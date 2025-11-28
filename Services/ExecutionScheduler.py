"""
ExecutionScheduler: Manages scheduled execution of test plans

Features:
- Schedule execution based on plan settings
- Support for cron expressions
- Handle recurring patterns (daily, weekly, monthly)
- Manage scheduled execution queue
- Track next execution times
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from auroqa.Services.ExecutionPlanService import ExecutionPlanService
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


class ExecutionScheduler:
    """Manages scheduled execution of test plans"""
    
    def __init__(self):
        """Initialize ExecutionScheduler"""
        self.logger = logging.getLogger(__name__)
        self.system = System()
        self.scheduler = BackgroundScheduler()
        self.plan_service = ExecutionPlanService()
        self.scheduled_jobs = {}  # Map of plan_id -> job_id
        self._lock = threading.Lock()
        
        # Configure scheduler
        self.scheduler.configure(
            jobstores={'default': {'type': 'memory'}},
            executors={'default': {'type': 'threadpool', 'max_workers': 5}},
            job_defaults={'coalesce': True, 'max_instances': 1}
        )
    
    def start(self):
        """Start the scheduler"""
        try:
            if not self.scheduler.running:
                self.scheduler.start()
                self.logger.info("ExecutionScheduler started")
                self._load_scheduled_plans()
        except Exception as e:
            self.logger.error(f"Error starting scheduler: {e}")
    
    def stop(self):
        """Stop the scheduler"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                self.logger.info("ExecutionScheduler stopped")
        except Exception as e:
            self.logger.error(f"Error stopping scheduler: {e}")
    
    def _load_scheduled_plans(self):
        """Load all scheduled plans from database"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, schedule_type, cron_expression, recurrence_pattern,
                               next_execution_at
                        FROM execution_suite_plans
                        WHERE status = 'active' AND schedule_type IN ('recurring', 'cron')
                        AND is_active = TRUE
                        """
                    )
                    
                    plans = cursor.fetchall()
                    for plan in plans:
                        plan_id, schedule_type, cron_expr, recurrence, next_exec = plan
                        self.schedule_plan(plan_id, schedule_type, cron_expr, recurrence)
                        
                    self.logger.info(f"Loaded {len(plans)} scheduled plans")
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error loading scheduled plans: {e}")
    
    def schedule_plan(
        self,
        plan_id: int,
        schedule_type: str,
        cron_expression: Optional[str] = None,
        recurrence_pattern: Optional[str] = None
    ) -> bool:
        """
        Schedule a plan for execution
        
        Args:
            plan_id: ID of the plan to schedule
            schedule_type: Type of schedule (manual, once, recurring, cron)
            cron_expression: Cron expression for cron scheduling
            recurrence_pattern: Pattern for recurring scheduling
            
        Returns:
            True if scheduling successful, False otherwise
        """
        try:
            with self._lock:
                # Remove existing job if any
                if plan_id in self.scheduled_jobs:
                    self.remove_schedule(plan_id)
                
                if schedule_type == 'cron' and cron_expression:
                    return self._schedule_cron(plan_id, cron_expression)
                elif schedule_type == 'recurring' and recurrence_pattern:
                    return self._schedule_recurring(plan_id, recurrence_pattern)
                elif schedule_type == 'once':
                    return self._schedule_once(plan_id)
                else:
                    self.logger.warning(f"Unknown schedule type: {schedule_type}")
                    return False
        except Exception as e:
            self.logger.error(f"Error scheduling plan {plan_id}: {e}")
            return False
    
    def _schedule_cron(self, plan_id: int, cron_expression: str) -> bool:
        """Schedule plan with cron expression"""
        try:
            trigger = CronTrigger.from_crontab(cron_expression)
            job = self.scheduler.add_job(
                self._execute_plan,
                trigger=trigger,
                args=[plan_id],
                id=f"plan_{plan_id}_cron",
                name=f"Plan {plan_id} (Cron)",
                replace_existing=True
            )
            
            self.scheduled_jobs[plan_id] = job.id
            self.logger.info(f"Scheduled plan {plan_id} with cron: {cron_expression}")
            
            # Update next execution time (handle None if scheduler not running yet)
            next_run = getattr(job, 'next_run_time', None)
            if next_run:
                self._update_next_execution(plan_id, next_run)
            
            return True
        except Exception as e:
            self.logger.error(f"Error scheduling cron for plan {plan_id}: {e}")
            return False
    
    def _schedule_recurring(self, plan_id: int, recurrence_pattern: str) -> bool:
        """Schedule plan with recurring pattern"""
        try:
            # Map recurrence patterns to intervals
            intervals = {
                'daily': {'days': 1},
                'weekly': {'weeks': 1},
                'monthly': {'days': 30},
                'hourly': {'hours': 1},
                'every_6_hours': {'hours': 6},
                'every_12_hours': {'hours': 12}
            }
            
            if recurrence_pattern not in intervals:
                self.logger.warning(f"Unknown recurrence pattern: {recurrence_pattern}")
                return False
            
            trigger = IntervalTrigger(**intervals[recurrence_pattern])
            job = self.scheduler.add_job(
                self._execute_plan,
                trigger=trigger,
                args=[plan_id],
                id=f"plan_{plan_id}_recurring",
                name=f"Plan {plan_id} ({recurrence_pattern})",
                replace_existing=True
            )
            
            self.scheduled_jobs[plan_id] = job.id
            self.logger.info(f"Scheduled plan {plan_id} with pattern: {recurrence_pattern}")
            
            # Update next execution time (handle None if scheduler not running yet)
            next_run = getattr(job, 'next_run_time', None)
            if next_run:
                self._update_next_execution(plan_id, next_run)
            
            return True
        except Exception as e:
            self.logger.error(f"Error scheduling recurring for plan {plan_id}: {e}")
            return False
    
    def _schedule_once(self, plan_id: int) -> bool:
        """Schedule plan for one-time execution"""
        try:
            plan = self.plan_service.get_execution_plan(plan_id)
            if not plan or not plan.get('scheduled_at'):
                self.logger.warning(f"Plan {plan_id} has no scheduled_at time")
                return False
            
            scheduled_time = plan['scheduled_at']
            if isinstance(scheduled_time, str):
                scheduled_time = datetime.fromisoformat(scheduled_time)
            
            # Don't schedule if time is in the past
            if scheduled_time <= datetime.now():
                self.logger.warning(f"Scheduled time for plan {plan_id} is in the past")
                return False
            
            job = self.scheduler.add_job(
                self._execute_plan,
                trigger='date',
                run_date=scheduled_time,
                args=[plan_id],
                id=f"plan_{plan_id}_once",
                name=f"Plan {plan_id} (Once)",
                replace_existing=True
            )
            
            self.scheduled_jobs[plan_id] = job.id
            self.logger.info(f"Scheduled plan {plan_id} for one-time execution at {scheduled_time}")
            
            # Update next execution time
            self._update_next_execution(plan_id, job.next_run_time)
            
            return True
        except Exception as e:
            self.logger.error(f"Error scheduling once for plan {plan_id}: {e}")
            return False
    
    def remove_schedule(self, plan_id: int) -> bool:
        """Remove schedule for a plan"""
        try:
            with self._lock:
                if plan_id in self.scheduled_jobs:
                    job_id = self.scheduled_jobs[plan_id]
                    self.scheduler.remove_job(job_id)
                    del self.scheduled_jobs[plan_id]
                    self.logger.info(f"Removed schedule for plan {plan_id}")
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error removing schedule for plan {plan_id}: {e}")
            return False
    
    def _execute_plan(self, plan_id: int):
        """Execute a plan (runs in scheduler thread)"""
        import threading
        try:
            self.logger.info(f"[Scheduler] Executing scheduled plan {plan_id}")
            
            # Create plan run
            run_id = self.plan_service.create_plan_run(
                plan_id=plan_id,
                triggered_by='schedule'
            )
            
            if run_id:
                self.logger.info(f"[Scheduler] Created execution run {run_id} for plan {plan_id}")
                
                # Execute in a separate thread to not block the scheduler
                from auroqa.Services.ParallelExecutionEngine import ParallelExecutionEngine
                engine = ParallelExecutionEngine()
                
                plan = self.plan_service.get_execution_plan(plan_id)
                max_parallel = plan.get('max_parallel_suites', 1) if plan else 1
                
                def run_execution():
                    try:
                        engine.execute_plan(plan_id=plan_id, run_id=run_id, max_parallel=max_parallel)
                    except Exception as ex:
                        self.logger.error(f"[Scheduler] Execution error for plan {plan_id}: {ex}")
                
                thread = threading.Thread(
                    target=run_execution,
                    name=f"ScheduledExec-{plan_id}-{run_id}",
                    daemon=True
                )
                thread.start()
            else:
                self.logger.error(f"[Scheduler] Failed to create execution run for plan {plan_id}")
        except Exception as e:
            self.logger.error(f"[Scheduler] Error executing plan {plan_id}: {e}")
    
    def _update_next_execution(self, plan_id: int, next_run_time):
        """Update next execution time in database"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE execution_suite_plans
                        SET next_execution_at = %s
                        WHERE id = %s
                        """,
                        (next_run_time, plan_id)
                    )
                    conn.commit()
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error updating next execution time for plan {plan_id}: {e}")
    
    def get_scheduled_jobs(self) -> List[Dict]:
        """Get all scheduled jobs"""
        try:
            jobs = []
            for job in self.scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time,
                    'trigger': str(job.trigger)
                })
            return jobs
        except Exception as e:
            self.logger.error(f"Error getting scheduled jobs: {e}")
            return []
    
    def get_job_status(self, plan_id: int) -> Optional[Dict]:
        """Get status of a scheduled job"""
        try:
            if plan_id in self.scheduled_jobs:
                job_id = self.scheduled_jobs[plan_id]
                job = self.scheduler.get_job(job_id)
                if job:
                    return {
                        'plan_id': plan_id,
                        'job_id': job.id,
                        'name': job.name,
                        'next_run_time': job.next_run_time,
                        'trigger': str(job.trigger),
                        'scheduled': True
                    }
            return {
                'plan_id': plan_id,
                'scheduled': False
            }
        except Exception as e:
            self.logger.error(f"Error getting job status for plan {plan_id}: {e}")
            return None
    
    def pause_schedule(self, plan_id: int) -> bool:
        """Pause schedule for a plan"""
        try:
            with self._lock:
                if plan_id in self.scheduled_jobs:
                    job_id = self.scheduled_jobs[plan_id]
                    self.scheduler.pause_job(job_id)
                    self.logger.info(f"Paused schedule for plan {plan_id}")
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error pausing schedule for plan {plan_id}: {e}")
            return False
    
    def resume_schedule(self, plan_id: int) -> bool:
        """Resume schedule for a plan"""
        try:
            with self._lock:
                if plan_id in self.scheduled_jobs:
                    job_id = self.scheduled_jobs[plan_id]
                    self.scheduler.resume_job(job_id)
                    self.logger.info(f"Resumed schedule for plan {plan_id}")
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error resuming schedule for plan {plan_id}: {e}")
            return False
    
    def calculate_next_execution(
        self,
        schedule_type: str,
        cron_expression: Optional[str] = None,
        recurrence_pattern: Optional[str] = None,
        scheduled_at: Optional[datetime] = None
    ) -> Optional[datetime]:
        """
        Calculate next execution time for a schedule
        
        Args:
            schedule_type: Type of schedule
            cron_expression: Cron expression
            recurrence_pattern: Recurrence pattern
            scheduled_at: Scheduled time for one-time execution
            
        Returns:
            Next execution datetime or None
        """
        try:
            if schedule_type == 'cron' and cron_expression:
                trigger = CronTrigger.from_crontab(cron_expression)
                return trigger.get_next_fire_time(None, datetime.now())
            elif schedule_type == 'recurring' and recurrence_pattern:
                intervals = {
                    'daily': timedelta(days=1),
                    'weekly': timedelta(weeks=1),
                    'monthly': timedelta(days=30),
                    'hourly': timedelta(hours=1),
                    'every_6_hours': timedelta(hours=6),
                    'every_12_hours': timedelta(hours=12)
                }
                if recurrence_pattern in intervals:
                    return datetime.now() + intervals[recurrence_pattern]
            elif schedule_type == 'once' and scheduled_at:
                return scheduled_at
            
            return None
        except Exception as e:
            self.logger.error(f"Error calculating next execution: {e}")
            return None


# Global scheduler instance
_scheduler_instance = None


def get_scheduler() -> ExecutionScheduler:
    """Get or create global scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ExecutionScheduler()
    return _scheduler_instance


def start_scheduler():
    """Start the global scheduler"""
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler():
    """Stop the global scheduler"""
    scheduler = get_scheduler()
    scheduler.stop()

-- Deleting a project or an environment failed with a foreign key error.
--
-- 1. Execution plans keep the environment they run on. The references had no ON DELETE rule,
--    so an environment used by any plan could not be deleted, and neither could its project
--    (a project deletes its environments by cascade). A plan whose environment is deleted keeps
--    running on the default one: the reference is set to NULL, as quick runs already have it.
-- 2. Execution plans had no reference to their project at all: deleting a project left them
--    behind. They now go with the project.
-- 3. Test cases kept their project with no ON DELETE rule, so a project with tests could not be
--    deleted. The UI promises "Test cases will be unassigned from this project but not deleted":
--    the reference is set to NULL.

ALTER TABLE execution_suite_plans DROP CONSTRAINT IF EXISTS execution_suite_plans_environment_id_fkey;
ALTER TABLE execution_suite_plans ADD CONSTRAINT execution_suite_plans_environment_id_fkey
    FOREIGN KEY (environment_id) REFERENCES environments(id) ON DELETE SET NULL;

ALTER TABLE execution_suite_plan_suites DROP CONSTRAINT IF EXISTS execution_suite_plan_suites_environment_id_fkey;
ALTER TABLE execution_suite_plan_suites ADD CONSTRAINT execution_suite_plan_suites_environment_id_fkey
    FOREIGN KEY (environment_id) REFERENCES environments(id) ON DELETE SET NULL;

ALTER TABLE execution_plan_suites DROP CONSTRAINT IF EXISTS execution_plan_suites_environment_id_fkey;
ALTER TABLE execution_plan_suites ADD CONSTRAINT execution_plan_suites_environment_id_fkey
    FOREIGN KEY (environment_id) REFERENCES environments(id) ON DELETE SET NULL;

-- Plans of projects that no longer exist cannot be reached from the UI
DELETE FROM execution_suite_plans WHERE project_id NOT IN (SELECT id FROM projects);
ALTER TABLE execution_suite_plans DROP CONSTRAINT IF EXISTS execution_suite_plans_project_id_fkey;
ALTER TABLE execution_suite_plans ADD CONSTRAINT execution_suite_plans_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE test_cases DROP CONSTRAINT IF EXISTS test_cases_project_id_fkey;
ALTER TABLE test_cases ADD CONSTRAINT test_cases_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;

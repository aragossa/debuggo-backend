import logging
import sys
from typing import Dict, Any, Optional
import json

from Utils.System import System
from Utils.AIHelper.HtmlAnalyzer import HtmlAnalyzer
from Services.ApiSchemaService import ApiSchemaService
from Utils.Connectors.db_utils import get_db_connection_context


class CombinedTestGenerationService:
    """
    Service to handle combined UI and API test generation with preconditions and teardown
    """
    
    def __init__(self):
        self.system = System()
        self.logger = self._setup_logger()
        self.html_analyzer = HtmlAnalyzer()
        self.api_service = ApiSchemaService()
        
    def _setup_logger(self):
        logger = logging.getLogger('CombinedTestGenerationService')
        logger.setLevel(logging.INFO)
        
        if logger.hasHandlers():
            logger.handlers.clear()
            
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def generate_combined_test(
        self, 
        test_case_id: int,
        test_case_name: str,
        test_case_description: str,
        page_source: str,
        page_url: str,
        client_id: str,
        project_id: str,
        environment_id: int = None,
        force_preconditions: bool = False
    ) -> Dict[str, Any]:
        """
        Main method to generate combined UI+API test with preconditions and teardown
        
        Flow:
        1. Check if preconditions are needed (Gemini decision or forced)
        2. If needed: Generate API precondition test case and steps
        3. If needed: Generate API teardown test case and steps  
        4. Generate UI test steps as usual
        5. Create dependencies between test cases
        """
        
        self.logger.info(f"🚀 Starting combined test generation for case {test_case_id}: {test_case_name}")
        
        # Build structured description for proper API generation
        structured_context = self._build_structured_description(test_case_name, test_case_description)
        self.logger.info(f"📝 Created structured context for API generation")
        self.logger.info(f"📋 Structured context preview: {structured_context[:200]}...")
        
        try:
            # Step 1: Check if preconditions are needed
            precondition_check = self.html_analyzer.check_preconditions_needed(
                test_case_name, 
                test_case_description, 
                force_preconditions
            )
            
            self.logger.info(f"📋 Precondition check result: {precondition_check}")
            
            if not precondition_check.get('needs_preconditions', False):
                # No preconditions needed - generate UI test as usual
                self.logger.info("✨ No preconditions needed, generating UI test only")
                return self._generate_ui_test_only(test_case_id, page_source, page_url)
            
            # Step 2: Get API schema for precondition generation
            schema_content = self._get_project_api_schema(project_id, client_id)
            if not schema_content:
                self.logger.warning("⚠️ Preconditions needed but no API schema found")
                return self._generate_ui_test_only(test_case_id, page_source, page_url)
            
            # Step 3: Generate precondition test case
            precondition_test_case_id = self._create_precondition_test_case(
                test_case_id, test_case_name, client_id, project_id, precondition_check, structured_context
            )
            
            # Step 4: Generate API steps for precondition (setup entities)
            self.logger.info("🔧 Generating API precondition steps...")
            try:
                precondition_success = self.api_service.generate_test_steps_iteratively(
                    test_case_id=precondition_test_case_id,
                    schema_content=schema_content,
                    client_id=client_id,
                    project_id=project_id,
                    environment_id=environment_id,
                    generation_context="precondition",
                    additional_context=structured_context
                )
                self.logger.info(f"🎯 Precondition generation result: {precondition_success}")
            except Exception as e:
                self.logger.error(f"❌ Precondition generation failed: {e}")
                precondition_success = False
            
            # Step 5: Generate UI test steps (main flow)
            self.logger.info(f"🖥️ Generating UI test steps for test case {test_case_id}...")
            self.logger.info(f"📄 Page source length: {len(page_source) if page_source else 0}")
            self.logger.info(f"🔗 Page URL: {page_url}")
            ui_success = self._generate_ui_test_only(test_case_id, page_source, page_url)
            self.logger.info(f"🎯 UI generation result: {ui_success}")
            
            # Step 6: Create teardown test case (AFTER UI generation)
            teardown_test_case_id = self._create_teardown_test_case(
                test_case_id, test_case_name, client_id, project_id, structured_context
            )
            
            # Step 7: Generate API steps for teardown (cleanup everything)
            self.logger.info("🧹 Generating API teardown steps...")
            try:
                teardown_success = self.api_service.generate_test_steps_iteratively(
                    test_case_id=teardown_test_case_id,
                    schema_content=schema_content,
                    client_id=client_id,
                    project_id=project_id,
                    environment_id=environment_id,
                    generation_context="teardown",
                    additional_context=f"{structured_context}\n\nTEARDOWN SPECIFIC CONTEXT: This teardown must clean up ALL entities created during the complete test flow: 1) Entities created by precondition test case {precondition_test_case_id}, 2) Any entities created or modified by the main UI test '{test_case_name}'. Focus on deleting recipient groups, clients, and other entities in reverse order of creation."
                )
                self.logger.info(f"🎯 Teardown generation result: {teardown_success}")
            except Exception as e:
                self.logger.error(f"❌ Teardown generation failed: {e}")
                teardown_success = False
            
            # Step 8: Create dependencies
            self._create_test_dependencies(test_case_id, precondition_test_case_id, teardown_test_case_id)
            
            return {
                "success": True,
                "main_test_case_id": test_case_id,
                "precondition_test_case_id": precondition_test_case_id if precondition_success else None,
                "teardown_test_case_id": teardown_test_case_id if teardown_success else None,
                "ui_generation_success": ui_success.get("success", False),
                "precondition_generation_success": precondition_success,
                "teardown_generation_success": teardown_success,
                "message": "Combined test generation completed successfully"
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error in combined test generation: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Combined test generation failed"
            }
    
    def _get_project_api_schema(self, project_id: str, client_id: str) -> Optional[str]:
        """Get the first available API schema for the project"""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT content 
                        FROM api_schemas 
                        WHERE project_id = %s AND client_id = %s 
                        ORDER BY created_at DESC 
                        LIMIT 1
                        """,
                        (project_id, client_id)
                    )
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            self.logger.error(f"Error getting API schema: {e}")
            return None
    
    def _create_precondition_test_case(
        self, 
        main_test_case_id: int, 
        main_test_name: str, 
        client_id: str, 
        project_id: str, 
        precondition_check: Dict[str, Any],
        structured_context: str
    ) -> int:
        """Create a new test case for API preconditions"""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get parent_id from main test case
                    cursor.execute(
                        "SELECT parent_id FROM test_cases WHERE id = %s",
                        (main_test_case_id,)
                    )
                    main_test_case = cursor.fetchone()
                    parent_id = main_test_case[0] if main_test_case else None
                    
                    cursor.execute(
                        """
                        INSERT INTO test_cases 
                        (name, description, parent_id, type, "order", client_id, project_id, test_type, is_precondition_template)
                        VALUES (%s, %s, %s, 'test', 1, %s, %s, 'api', %s)
                        RETURNING id
                        """,
                        (
                            f"[PRECONDITION] {main_test_name}",
                            f"{structured_context}\n\nReason for preconditions: {precondition_check.get('reason', '')}",
                            parent_id,
                            client_id,
                            project_id,
                            True
                        )
                    )
                    precondition_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    self.logger.info(f"✅ Created precondition test case: {precondition_id}")
                    self.logger.info(f"📝 Precondition description starts with: {structured_context[:150]}...")
                    return precondition_id
                    
        except Exception as e:
            self.logger.error(f"Error creating precondition test case: {e}")
            raise
    
    def _create_teardown_test_case(
        self, 
        main_test_case_id: int, 
        main_test_name: str, 
        client_id: str, 
        project_id: str,
        structured_context: str
    ) -> int:
        """Create a new test case for API teardown"""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get parent_id from main test case
                    cursor.execute(
                        "SELECT parent_id FROM test_cases WHERE id = %s",
                        (main_test_case_id,)
                    )
                    main_test_case = cursor.fetchone()
                    parent_id = main_test_case[0] if main_test_case else None
                    
                    cursor.execute(
                        """
                        INSERT INTO test_cases 
                        (name, description, parent_id, type, "order", client_id, project_id, test_type, is_precondition_template)
                        VALUES (%s, %s, %s, 'test', 1, %s, %s, 'api', %s)
                        RETURNING id
                        """,
                        (
                            f"[TEARDOWN] {main_test_name}",
                            f"{structured_context}\n\nTeardown purpose: Clean up all entities created during preconditions and main test execution.",
                            parent_id,
                            client_id,
                            project_id,
                            False
                        )
                    )
                    teardown_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    self.logger.info(f"✅ Created teardown test case: {teardown_id}")
                    return teardown_id
                    
        except Exception as e:
            self.logger.error(f"Error creating teardown test case: {e}")
            raise
    
    def _create_test_dependencies(
        self, 
        main_test_case_id: int, 
        precondition_test_case_id: int, 
        teardown_test_case_id: int
    ):
        """Create dependency relationships between test cases"""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Create precondition dependency
                    cursor.execute(
                        """
                        INSERT INTO test_dependencies 
                        (dependent_test_case_id, prerequisite_test_case_id, dependency_type, execution_order)
                        VALUES (%s, %s, 'precondition', 1)
                        """,
                        (main_test_case_id, precondition_test_case_id)
                    )
                    
                    # Create teardown dependency
                    cursor.execute(
                        """
                        INSERT INTO test_dependencies 
                        (dependent_test_case_id, prerequisite_test_case_id, dependency_type, execution_order)
                        VALUES (%s, %s, 'teardown', 1)
                        """,
                        (main_test_case_id, teardown_test_case_id)
                    )
                    
                    conn.commit()
                    self.logger.info("✅ Created test dependencies")
                    
        except Exception as e:
            self.logger.error(f"Error creating test dependencies: {e}")
            raise

    def _get_environment_variables(self, test_case_id: int) -> dict:
        """Get environment variables for the test case's project."""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT env.base_url, env.login, env.password
                        FROM test_cases tc
                        JOIN projects p ON tc.project_id = p.id
                        JOIN environments env ON p.id = env.project_id
                        WHERE tc.id = %s 
                        LIMIT 1
                    """, (test_case_id,))
                    result = cursor.fetchone()
                    
                    if result:
                        base_url, login, password = result
                        env_vars = {}
                        if base_url:
                            env_vars['base_url'] = base_url
                        if login:
                            env_vars['login'] = login
                        if password:
                            env_vars['password'] = password
                        return env_vars
                    else:
                        self.logger.warning(f"No environment found for test case {test_case_id}")
                        return {}
        except Exception as e:
            self.logger.error(f"Error getting environment variables: {e}")
            return {}

    def _extract_business_keywords(self, description: str) -> list:
        """Extract key business terms from test description."""
        business_terms = []
        description_lower = description.lower()
        
        # Common UI business actions
        action_keywords = {
            'create': ['create', 'new', 'add', 'build', 'make'],
            'edit': ['edit', 'modify', 'update', 'change'],
            'delete': ['delete', 'remove', 'cancel'],
            'view': ['view', 'see', 'display', 'show', 'list'],
            'navigate': ['go to', 'navigate', 'visit', 'open']
        }
        
        # Business entities
        entity_keywords = ['recipient', 'group', 'campaign', 'client', 'user', 'account', 'project']
        
        for action, synonyms in action_keywords.items():
            if any(synonym in description_lower for synonym in synonyms):
                business_terms.append(action)
                
        for entity in entity_keywords:
            if entity in description_lower:
                business_terms.append(entity)
                
        return business_terms

    def _extract_page_context(self, page_source: str) -> dict:
        """Extract context information from current page HTML."""
        import re
        context = {
            'title': 'Unknown',
            'interactive_elements': [],
            'navigation_items': [],
            'form_fields': []
        }
        
        if not page_source:
            return context
            
        # Extract page title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', page_source, re.IGNORECASE)
        if title_match:
            context['title'] = title_match.group(1).strip()
            
        # Extract interactive elements
        button_matches = re.findall(r'<button[^>]*>(.*?)</button>', page_source, re.IGNORECASE | re.DOTALL)
        link_matches = re.findall(r'<a[^>]*>(.*?)</a>', page_source, re.IGNORECASE | re.DOTALL)
        
        context['interactive_elements'] = [btn.strip() for btn in button_matches[:10]]  # Limit results
        context['navigation_items'] = [link.strip() for link in link_matches[:10]]
        
        return context

    def _build_enhanced_prompt(self, step_order: int, test_case_name: str, test_case_description: str, 
                              prev_step_description: str, page_context: dict, business_keywords: list) -> str:
        """Build an enhanced prompt with business workflow guidance."""
        
        # Determine workflow stage
        if step_order <= 2:
            workflow_stage = "INITIAL_ACCESS"
            stage_guidance = "Focus on authentication and reaching the main application area."
        elif 'login' in prev_step_description.lower() and 'success' in prev_step_description.lower():
            workflow_stage = "POST_LOGIN_NAVIGATION"
            stage_guidance = f"Navigate to the relevant section for: {', '.join(business_keywords)}"
        else:
            workflow_stage = "BUSINESS_ACTION"
            stage_guidance = "Perform the main business action described in the test objective."
            
        return f"""
ENHANCED UI TEST STEP GENERATION

BUSINESS OBJECTIVE: {test_case_description}
CURRENT STEP: {step_order}
WORKFLOW STAGE: {workflow_stage}

CONTEXT ANALYSIS:
- Current page: {page_context.get('title', 'Unknown')}
- Available actions: {', '.join(page_context.get('interactive_elements', [])[:5])}
- Navigation options: {', '.join(page_context.get('navigation_items', [])[:5])}
- Previous step result: {prev_step_description}

BUSINESS KEYWORDS TO TARGET: {', '.join(business_keywords)}

WORKFLOW REQUIREMENTS:
1. Complete end-to-end user journey for: {test_case_description}
2. Each step should advance toward the business goal
3. Include realistic navigation patterns (menu → section → action)
4. Verify success after each major action

STAGE-SPECIFIC GUIDANCE: {stage_guidance}

COMMON UI WORKFLOWS FOR REFERENCE:
- CREATE WORKFLOW: Navigate → Find "New/Add" button → Fill form → Submit → Verify
- EDIT WORKFLOW: Navigate → Find item → Click edit → Modify → Save → Verify  
- LIST/VIEW WORKFLOW: Navigate → Find section → Browse items → Verify content

STEP GENERATION RULES:
1. If just logged in: Look for navigation to business section (recipients, campaigns, etc.)
2. If in business section: Look for action buttons (New, Add, Create, etc.)
3. If in form: Fill required fields with realistic test data
4. If submitting: Look for submit/save buttons
5. Always include verification of step success

VERIFICATION REQUIREMENTS:
- Navigation steps: Verify new page/section loaded (check title, heading, or unique content)
- Form interactions: Verify form fields are filled correctly
- Button clicks: Verify expected result (new page, modal, success message)
- Creation actions: Verify item appears in list OR success notification
- Login actions: Verify dashboard/main application area is accessible

STEP COMPLETION CRITERIA:
Each generated step MUST include:
- Clear action to perform
- Specific element to target (xpath/css selector)
- Expected result/verification
- Value to input (if applicable)

CURRENT STEP FOCUS:
Based on workflow stage "{workflow_stage}" and business objective "{test_case_description}",
generate the next logical UI action that progresses toward completing this business goal.

IMPORTANT: Include verification in your step to confirm the action succeeded.
Generate step {step_order} that moves closer to: {test_case_description}
"""

    def _build_structured_description(self, test_case_name: str, original_description: str) -> str:
        """Build a structured description that separates preconditions from main UI actions."""
        
        # Extract business action from name/description
        business_action = "perform UI actions"
        if "create" in test_case_name.lower():
            entity = ""
            for word in ['recipient', 'group', 'campaign', 'client', 'user', 'account']:
                if word in test_case_name.lower():
                    entity = word
                    break
            if entity:
                business_action = f"create a new {entity} via UI"
        elif "edit" in test_case_name.lower() or "update" in test_case_name.lower():
            business_action = "edit existing item via UI"
        elif "delete" in test_case_name.lower():
            business_action = "delete item via UI"
            
        return f"""
STRUCTURED TEST DESCRIPTION:

preconditions: 
- Authenticate user to get API access
- Create any required dependency entities (clients, accounts, etc.) via API
- Set up test data needed for the main UI workflow
- DO NOT perform the main business action (that's for the UI test)

test case: 
- Login to the web application
- Navigate to the appropriate section in the UI
- {business_action}
- Verify the action was successful
- Complete the end-to-end user workflow

teardown:
- Clean up any entities created during the test
- Reset application state for next test

Original description: {original_description}
Business objective: {business_action}
"""

    def _generate_ui_test_only(self, test_case_id: int, page_source: str = "", page_url: str = "") -> bool:
        """
        Generate UI test steps without API preconditions.
        This is used when no API preconditions are needed.
        """
        self.logger.info(f"🚀 Starting UI generation for test case {test_case_id}")
        self.logger.info(f"📊 Input params - page_source: {len(page_source)} chars, page_url: {page_url}")
        
        # Get environment variables for variable substitution
        environment_vars = self._get_environment_variables(test_case_id)
        from Utils.BrowserAutomation.EnvHelper import EnvHelper
        env_helper = EnvHelper(environment_vars)
        self.logger.info(f"🌍 Environment variables loaded: {list(environment_vars.keys()) if environment_vars else 'None'}")
        
        # Register UI generation in Redis for status bar display
        try:
            from Utils.System import System
            import redis
            system = System()
            r = redis.Redis(host=system.redis_host, port=system.redis_port, db=0, decode_responses=True)
            r.set(f"ui_test_generating:{test_case_id}", f"UI test generation for case {test_case_id}", ex=3600)  # Expires in 1 hour
            self.logger.info(f"📊 Registered UI generation in Redis for status bar")
        except Exception as redis_error:
            self.logger.warning(f"⚠️ Failed to register UI generation in Redis: {redis_error}")
        
        try:
            # If no page_source provided, attempt to get HTML from browser
            if not page_source or len(page_source) < 100:
                self.logger.info("🌐 No page_source provided, attempting to get real HTML from browser...")
                try:
                    # Initialize browser to get real page HTML
                    from Utils.BrowserAutomation.TestRunner import TestRunner
                    temp_test_runner = TestRunner(13, test_case_id)
                    
                    # Get the actual base URL from environment
                    actual_base_url = "https://lucyqa.lucysecurity.com"  # Default fallback
                    
                    try:
                        # Try to get base_url from project environment
                        with get_db_connection_context() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    SELECT env.base_url 
                                    FROM test_cases tc
                                    JOIN projects p ON tc.project_id = p.id
                                    JOIN environments env ON p.id = env.project_id
                                    WHERE tc.id = %s 
                                    LIMIT 1
                                """, (test_case_id,))
                                result = cursor.fetchone()
                                if result and result[0]:
                                    actual_base_url = result[0]
                                    self.logger.info(f"📍 Using base_url from environment: {actual_base_url}")
                    except Exception as env_error:
                        self.logger.warning(f"⚠️ Could not get base_url from environment: {env_error}")
                        self.logger.info(f"🔄 Using fallback base_url: {actual_base_url}")
                    
                    # Navigate to the actual base URL to get real HTML  
                    temp_test_runner.execute_step(
                        action="navigate",
                        element_path=actual_base_url,
                        value=None,
                        by_strategy=None
                    )
                    
                    # Get the real page source
                    if temp_test_runner.browser and temp_test_runner.browser.driver:
                        real_page_source = temp_test_runner.browser.driver.page_source
                        self.logger.info(f"🔍 Retrieved page source length: {len(real_page_source) if real_page_source else 0}")
                        if real_page_source:
                            self.logger.info(f"🔍 Page source preview (first 200 chars): {real_page_source[:200]}")
                        
                        if real_page_source and len(real_page_source) > 100:
                            page_source = real_page_source
                            page_url = temp_test_runner.browser.driver.current_url
                            self.logger.info(f"✅ Retrieved real HTML from browser ({len(page_source)} chars)")
                            
                            # Don't clean up browser yet - we need it for screenshots during generation
                            # Store the browser for later use
                            self.test_runner = temp_test_runner
                            self.logger.info("🔄 Keeping browser session active for screenshots and step execution")
                        else:
                            raise Exception(f"Retrieved page source is empty or too small: {len(real_page_source) if real_page_source else 0} chars")
                    else:
                        raise Exception("Browser not properly initialized")
                        
                except Exception as browser_error:
                    self.logger.warning(f"⚠️ Failed to get real HTML from browser: {browser_error}")
                    self.logger.info("🔄 Falling back to improved placeholder HTML...")
                    
                    # Fallback with correct element IDs
                    page_source = """<html><head><title>Login - Lucy Security</title></head><body>
                    <div class="login-container">
                        <h1>Login to Lucy Security</h1>
                        <form id="LoginForm" class="form-horizontal">
                            <div class="form-group">
                                <label for="LoginForm_email">Email</label>
                                <input placeholder="Enter your Email" type="text" class="form-control" id="LoginForm_email" name="LoginForm[email]" maxlength="255" value="" autocomplete="off">
                            </div>
                            <div class="form-group">
                                <label for="LoginForm_password">Password</label>
                            <input placeholder="Password" type="password" class="form-control" id="LoginForm_password" name="LoginForm[password]" maxlength="255" autocomplete="off">
                        </div>
                        <button type="submit" id="login-btn" class="btn btn-primary">Log In</button>
                    </form>
                    </div></body></html>"""
                    page_url = "%base_url%"
                    self.logger.info(f"🔄 Using improved placeholder HTML with real element IDs ({len(page_source)} chars)")
            
            page_url = "%base_url%"
            
            # Clear any existing steps, dependencies, and associated test cases
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get existing precondition and teardown test case IDs before deleting dependencies
                    cursor.execute("""
                        SELECT prerequisite_test_case_id, dependency_type 
                        FROM test_dependencies 
                        WHERE dependent_test_case_id = %s 
                        AND dependency_type IN ('precondition', 'teardown')
                    """, (test_case_id,))
                    
                    dependent_test_cases = cursor.fetchall()
                    self.logger.info(f"🔍 Found {len(dependent_test_cases)} existing dependencies to clear")
                    
                    # Delete dependency relationships first
                    cursor.execute("DELETE FROM test_dependencies WHERE dependent_test_case_id = %s", (test_case_id,))
                    self.logger.info(f"🗑️ Cleared existing dependencies for test case {test_case_id}")
                    
                    # Delete steps from the dependent test cases (preconditions/teardowns)
                    for dep_test_case_id, dep_type in dependent_test_cases:
                        cursor.execute("DELETE FROM test_steps WHERE test_case_id = %s", (dep_test_case_id,))
                        self.logger.info(f"🗑️ Cleared {dep_type} steps for test case {dep_test_case_id}")
                    
                    # Delete the main test case steps
                    cursor.execute("DELETE FROM test_steps WHERE test_case_id = %s", (test_case_id,))
                    self.logger.info(f"🗑️ Cleared existing UI steps for test case {test_case_id}")
                    
                    conn.commit()
            
            # Get actual test case info from database for better context
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT name, description FROM test_cases WHERE id = %s", (test_case_id,))
                    result = cursor.fetchone()
                    if result:
                        test_case_name = result[0]
                        original_description = result[1] or "UI test case"
                    else:
                        test_case_name = "recipient group UI test"  
                        original_description = "UI test with login flow for recipient groups functionality"
            
            # Build enhanced test description with proper precondition separation
            test_case_description = self._build_structured_description(test_case_name, original_description)
            structured_context = test_case_description  # Save for API generation
            
            # Extract business context for enhanced prompting
            business_keywords = self._extract_business_keywords(test_case_description)
            self.logger.info(f"🎯 Business keywords identified: {business_keywords}")
            self.logger.info(f"📝 Enhanced test description: {test_case_description}")
            
            # First, add a navigation step to %base_url%
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO test_steps (
                            test_case_id, step_order, action, target, element_path,
                            value, description, expected_result
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        test_case_id, 1, 'navigate', '%base_url%', '%base_url%',
                        '', 'Navigate to the application base URL', 'Step completed successfully'
                    ))
            
            self.logger.info("✅ Added initial navigation step to %base_url%")
            
            steps_generated = 1
            max_steps = 10
            step_order = 2  # Start from step 2 since step 1 is navigation
            prev_step_description = "Navigated to application base URL"
            
            while steps_generated < max_steps:
                self.logger.info(f"🔄 Generating UI step {step_order}...")
                
                try:
                    # Get current page context for enhanced prompting
                    current_page_source = ""
                    if hasattr(self, 'test_runner') and self.test_runner and self.test_runner.browser:
                        try:
                            current_page_source = self.test_runner.browser.driver.page_source
                        except:
                            pass
                    
                    page_context = self._extract_page_context(current_page_source)
                    
                    # Use enhanced prompt with business workflow guidance
                    next_prompt = self._build_enhanced_prompt(
                        step_order, test_case_name, test_case_description,
                        prev_step_description, page_context, business_keywords
                    )
                    
                    # Take screenshot of current page state for Gemini analysis
                    screenshot_path = None
                    try:
                        if hasattr(self, 'test_runner') and self.test_runner and self.test_runner.browser:
                            screenshot_path = self.test_runner.browser.take_screenshot(f"step_{step_order}_analysis")
                            self.logger.info(f"📸 Screenshot taken for analysis: {screenshot_path}")
                        else:
                            self.logger.warning("⚠️ No browser available for screenshot during analysis")
                    except Exception as screenshot_error:
                        self.logger.warning(f"⚠️ Failed to take screenshot for analysis: {screenshot_error}")
                    
                    # Debug: Log what HTML is being sent to Gemini
                    self.logger.info(f"🔍 Sending HTML to Gemini - length: {len(page_source)} chars")
                    self.logger.info(f"🔍 HTML preview being sent (first 200 chars): {page_source[:200]}")
                    
                    next_step, description, action, element_path, path_type, value = self.html_analyzer.html_analyzer(
                        test_case_id=test_case_id,
                        html_code=page_source,
                        test_name=test_case_name,
                        test_description=test_case_description,
                        step_order=step_order,
                        next_prompt=next_prompt,
                        prev_step_description=prev_step_description,
                        screenshot_path=screenshot_path
                    )
                    
                    # Set expected_result from next_step
                    expected_result = next_step or "Step completed successfully"
                    target = element_path  # Use element_path as target
                    
                    # Save the step to database
                    try:
                        with get_db_connection_context() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    INSERT INTO test_steps (
                                        test_case_id, step_order, action, target, element_path,
                                        path_type, value, description, expected_result
                                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """, (
                                    test_case_id, step_order, action, target, element_path,
                                    path_type, value, description, expected_result
                                ))
                                conn.commit()  # Explicit commit
                                self.logger.info(f"💾 Database insert successful for step {step_order}")
                    except Exception as db_error:
                        self.logger.error(f"❌ Database insert failed for step {step_order}: {db_error}")
                        self.logger.error(f"Data: test_case_id={test_case_id}, step_order={step_order}, action={action}, target={target}, element_path={element_path}, path_type={path_type}, value={value}")
                        raise db_error
                    
                    self.logger.info(f"✅ Generated step {step_order}: {action} - {description}")
                    
                    # Execute the step immediately for feedback loop (like TestRunner does)
                    try:
                        self.logger.info(f"▶️ Executing step {step_order} for feedback...")
                        
                        # Initialize browser if not done yet
                        if not hasattr(self, 'test_runner') or not self.test_runner:
                            from Utils.BrowserAutomation.TestRunner import TestRunner
                            self.test_runner = TestRunner(13, test_case_id)  # Use a default user_id
                            
                        # Process environment variables in the value (e.g., %login%, %password%)
                        processed_value = env_helper.process_variables(value or '') if value else ''
                        if processed_value != (value or ''):
                            self.logger.info(f"🔄 Variable substitution: '{value}' → '{processed_value}'")
                        
                        # Execute the step with correct parameters
                        self.test_runner.execute_step(
                            action=action,
                            element_path=element_path,
                            value=processed_value,
                            by_strategy=path_type or 'xpath'
                        )
                        
                        # If we reach here, execution was successful (no exception thrown)
                        self.logger.info(f"✅ Step {step_order} executed successfully")
                        
                        # Take screenshot after step execution for test step record
                        try:
                            step_screenshot_path = self.test_runner.browser.take_screenshot(f"step_{step_order}_executed")
                            self.logger.info(f"📸 Step screenshot saved: {step_screenshot_path}")
                            
                            # Update database with screenshot path
                            try:
                                with get_db_connection_context() as conn:
                                    with conn.cursor() as cursor:
                                        cursor.execute("""
                                            UPDATE test_steps 
                                            SET screenshot_path = %s 
                                            WHERE test_case_id = %s AND step_order = %s
                                        """, (step_screenshot_path, test_case_id, step_order))
                                        conn.commit()
                                self.logger.info(f"📸 Screenshot path saved to database for step {step_order}")
                            except Exception as db_screenshot_error:
                                self.logger.warning(f"⚠️ Failed to save screenshot path to database: {db_screenshot_error}")
                                
                        except Exception as screenshot_error:
                            self.logger.warning(f"⚠️ Failed to take step screenshot: {screenshot_error}")
                        
                        # Update page_source with current page HTML for next iteration
                        current_html = self.test_runner.browser.driver.page_source
                        page_source = current_html  # Limit size
                        self.logger.info(f"📄 Updated page source: {len(page_source)} chars")
                            
                    except Exception as exec_error:
                        self.logger.warning(f"⚠️ Step {step_order} execution error: {exec_error}")
                        self.logger.warning("Continuing with generation using original page source")
                    
                    steps_generated += 1
                    step_order += 1
                    prev_step_description = description
                    
                    # Check if this is a final step (like assertion or completion)
                    if action.lower() in ['assert', 'assert_text_contains'] and 'success' in description.lower():
                        self.logger.info("🎯 Detected completion step, finishing generation")
                        break
                        
                except Exception as step_error:
                    self.logger.error(f"⚠️ Failed to generate step {step_order}: {step_error}")
                    import traceback
                    self.logger.error(f"Full traceback: {traceback.format_exc()}")
                    break
            
            self.logger.info(f"✅ Generated {steps_generated} UI test steps using iterative approach")
            
            # Clean up browser resources
            try:
                if hasattr(self, 'test_runner') and self.test_runner:
                    # TestRunner doesn't have a cleanup method, let's close browser directly
                    if hasattr(self.test_runner, 'browser') and self.test_runner.browser:
                        self.test_runner.browser.quit()
                        self.logger.info("🧹 Browser cleanup completed")
                    else:
                        self.logger.info("🧹 No browser to cleanup")
            except Exception as cleanup_error:
                self.logger.warning(f"⚠️ Browser cleanup error: {cleanup_error}")
            
            # Clean up Redis generation status
            try:
                from Utils.System import System
                import redis
                system = System()
                r = redis.Redis(host=system.redis_host, port=system.redis_port, db=0, decode_responses=True)
                r.delete(f"ui_test_generating:{test_case_id}")
                self.logger.info(f"🧹 Removed UI generation status from Redis")
            except Exception as redis_error:
                self.logger.warning(f"⚠️ Failed to clean up Redis status: {redis_error}")
            
            return {"success": True, "steps_count": steps_generated}
            
        except Exception as e:
            self.logger.error(f"❌ Error generating UI test for case {test_case_id}: {e}")
            import traceback
            self.logger.error(f"📋 Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

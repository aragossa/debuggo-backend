-- public.test_cases definition
CREATE TABLE  IF NOT EXISTS  public.test_cases (
	id serial4 NOT NULL,
	"name" text NOT NULL,
	description text NULL,
	parent_id int4 NULL,
	"type" text NOT NULL,
	"order" int4 DEFAULT 1 NOT NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	test_case_id int4 NULL,
	curl text NULL,
	python_script text NULL,
	CONSTRAINT test_cases_pkey PRIMARY KEY (id),
	CONSTRAINT test_cases_type_check CHECK ((type = ANY (ARRAY['root'::text, 'test'::text, 'group'::text]))),
	CONSTRAINT test_cases_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.test_cases(id) ON DELETE CASCADE
);


-- public.test_runs definition
CREATE TABLE IF NOT EXISTS  public.test_runs (
	id serial4 NOT NULL,
	test_case_id int4 NOT NULL,
	run_date timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	"result" text NOT NULL,
	"exception" text NULL,
	duration float4 NULL,
	"stdout" text NULL,
	stderr text NULL,
	additional_info text NULL,
	CONSTRAINT test_runs_pkey PRIMARY KEY (id)
);

-- public.test_runs foreign keys
ALTER TABLE public.test_runs ADD CONSTRAINT test_runs_test_case_id_fkey FOREIGN KEY (test_case_id) REFERENCES public.test_cases(id) ON DELETE CASCADE;


-- public.test_steps definition
CREATE TABLE IF NOT EXISTS  public.test_steps (
	id serial4 NOT NULL,
	test_case_id int4 NOT NULL,
	step_order int4 NOT NULL,
	description text NOT NULL,
	expected_result text NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	"action" text DEFAULT 'click'::text NOT NULL,
	element_path text NULL,
	value text NULL,
	path_type text NULL,
	CONSTRAINT test_steps_pkey PRIMARY KEY (id),
	CONSTRAINT valid_action CHECK ((action = ANY (ARRAY['click'::text, 'type'::text, 'select'::text, 'hover'::text, 'wait'::text, 'assert'::text, 'scroll'::text, 'clear'::text, 'navigate'::text, 'press_key'::text]))),
	CONSTRAINT valid_path_type CHECK ((path_type = ANY (ARRAY['css'::text, 'xpath'::text])))
);

-- public.test_steps foreign keys
ALTER TABLE public.test_steps ADD CONSTRAINT test_steps_test_case_id_fkey FOREIGN KEY (test_case_id) REFERENCES public.test_cases(id) ON DELETE CASCADE;


-- public.test_variables definition
CREATE TABLE IF NOT EXISTS  public.test_variables (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	"name" text NULL,
	value varchar NULL,
	CONSTRAINT test_variables_pkey PRIMARY KEY (id)
);
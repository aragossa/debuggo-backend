CREATE TABLE test_cases_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    parent_id INTEGER REFERENCES test_cases(id) ON DELETE CASCADE,
    type TEXT CHECK(type IN ('root', 'child', 'grandchild', 'step', 'test', 'group')) NOT NULL,
    "order" INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    test_case_id INTEGER,
    curl TEXT
);

-- Insert Root Nodes
INSERT INTO test_cases (name, type, "order") VALUES
('Root Node 1', 'root', 1),
('Root Node 2', 'root', 2);

-- Insert Child Nodes under Root Node 1
INSERT INTO test_cases (name, parent_id, type, "order") VALUES
('Child Node 1', 1, 'child', 1),
('Child Node 2', 1, 'child', 2);

-- Insert Grandchild Node under Child Node 2
INSERT INTO test_cases (name, parent_id, type, "order") VALUES
('Grandchild Node', 3, 'grandchild', 1);


WITH RECURSIVE TestCaseHierarchy AS (
    SELECT id, name, parent_id, type, "order", curl, test_case_id
    FROM test_cases
    WHERE parent_id IS NULL  -- Start with root nodes
    UNION ALL
    SELECT tc.id, tc.name, tc.parent_id, tc.type, tc."order"
    FROM test_cases tc
    INNER JOIN TestCaseHierarchy tch ON tc.parent_id = tch.id
)
SELECT * FROM TestCaseHierarchy
ORDER BY "order";
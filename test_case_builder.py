from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


# Function to recursively build tree structure from flat data
def build_tree(nodes, parent_id=None):
    tree = []
    for node in nodes:
        if node['parent_id'] == parent_id:
            children = build_tree(nodes, node['id'])
            if children:
                node['children'] = children
            else:
                node['children'] = []
            tree.append(node)
    return tree

# Connect to the SQLite database
def fetch_tree_data(client_id):
    # Establish connection to the PostgreSQL database
    conn = get_db_connection()
    cursor = conn.cursor()

    # Execute the recursive query
    cursor.execute('''
        WITH RECURSIVE TestCaseHierarchy AS (
            SELECT id, name, parent_id, type, "order", curl, test_case_id, client_id, project_id
            FROM test_cases
            WHERE parent_id IS NULL AND client_id = ?  -- Start with root nodes
            UNION ALL
            SELECT tc.id, tc.name, tc.parent_id, tc.type, tc."order", tc.curl, tc.test_case_id, tc.client_id, tc.project_id
            FROM test_cases tc
            JOIN TestCaseHierarchy tch ON tc.parent_id = tch.id
        )
        SELECT * FROM TestCaseHierarchy
        ORDER BY parent_id NULLS FIRST, "order";
    ''', (client_id,))

    # Fetch all results
    result = cursor.fetchall()

    # Return the database connection to the pool
    return_db_connection(conn)

    # Convert the result into a list of dictionaries
    nodes = []
    for row in result:
        nodes.append({
            'id': row[0],
            'name': row[1],
            'parent_id': row[2],
            'type': row[3],
            'order': row[4],
            'curl': row[5] if row[5] is not None else None,
            'test_case_id': row[6] if row[6] is not None else None,
            'client_id': row[7],
            'project_id': row[8]
        })

    return nodes

# Main function to generate the JSON object
def get_tests_tree(client_id_or_test_cases):
    # Check if we received a list of test cases or a client_id
    if isinstance(client_id_or_test_cases, list):
        # We received a list of test cases, use it directly
        nodes = client_id_or_test_cases
    else:
        # We received a client_id, fetch the test cases from the database
        nodes = fetch_tree_data(client_id_or_test_cases)

    # Build the hierarchical tree structure
    tree_data = build_tree(nodes)

    # Return the tree structure
    return tree_data
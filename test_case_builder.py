import json

from Utils.DbConnector import DbConnector


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
def fetch_tree_data():
    # Establish connection to the SQLite database
    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()

    # Execute the recursive query
    cursor.execute('''
        WITH RECURSIVE TestCaseHierarchy AS (
            SELECT id, name, parent_id, type, "order", curl, test_case_id
            FROM test_cases
            WHERE parent_id IS NULL  -- Start with root nodes
            UNION ALL
            SELECT tc.id, tc.name, tc.parent_id, tc.type, tc."order", tc.curl, tc.test_case_id
            FROM test_cases tc
            INNER JOIN TestCaseHierarchy tch ON tc.parent_id = tch.id
        )
        SELECT * FROM TestCaseHierarchy
        ORDER BY "order";
    ''')

    # Fetch all results
    result = cursor.fetchall()

    # Close the database connection
    conn.close()

    # Convert the result into a list of dictionaries
    nodes = []
    for row in result:

        nodes.append({
            'id': row[0],
            'name': row[1],
            'parent_id': row[2],
            'curl': row[5] if row[5] is not None else None,
            'test_case_id': row[6] if row[6] is not None else None
        })

    return nodes

# Main function to generate the JSON object
def get_tests_tree():
    # Fetch the flat test case data from the database
    nodes = fetch_tree_data()

    # Build the hierarchical tree structure
    tree_data = build_tree(nodes)

    # Convert the tree structure to JSON format
    return tree_data
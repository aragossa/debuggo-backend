import sqlite3

def clear_all_data():
    # Establish connection to the SQLite database
    conn = sqlite3.connect('database.sqlite')
    cursor = conn.cursor()

    # Execute the recursive query
    cursor.execute('''
    DELETE FROM test_cases ;
    ''')
    cursor.execute('''
    DELETE FROM test_steps ;
    ''')
    cursor.execute('''
    DELETE FROM test_runs ;
    ''')
    conn.commit()
    # Close the database connection
    conn.close()

    return True
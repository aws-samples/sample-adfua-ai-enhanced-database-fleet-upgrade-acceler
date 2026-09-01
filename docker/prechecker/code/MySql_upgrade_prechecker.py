from venv import logger
import pymysql as mysql
import traceback
import sys
import os
import json
from typing import List, Dict
from datetime import datetime, timezone
import urllib
import boto3,threading
from botocore.exceptions import ClientError
import configparser
import shlex
import subprocess  # nosec B404 # Required for MySQL Shell utility execution
from typing import Dict
import urllib.parse

def _mysql_ssl_args():
    """
    Build TLS args for pymysql. When the RDS global CA bundle is present
    (see Dockerfile), the server certificate is verified. Otherwise TLS is
    still required (encrypted, without CA pinning) so credentials never
    traverse the network in cleartext.
    """
    ca_path = os.environ.get("RDS_CA_BUNDLE", "/etc/ssl/certs/rds-global-bundle.pem")
    if os.path.exists(ca_path):
        return {"ca": ca_path}
    print(f"WARNING: RDS CA bundle not found at {ca_path}; using TLS without CA verification")
    return {}

def get_credentials_from_secret(secret_name, region):
    """Get username and password from AWS Secrets Manager"""
    try:
        secrets_client = boto3.client('secretsmanager', region_name=region)
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        return secret.get('username'), secret.get('password')
    except Exception as e:
        print(f"Error getting credentials from secret {secret_name}: {e}")
        raise

def get_rds_connection(region):
    rds_client = boto3.client('rds', region_name=region)
    return rds_client

def get_rds_instance_endpoint(rds,instance_identifier):
    try:
        response = rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
        end_point = response['DBInstances'][0]['Endpoint']['Address']
        port = response['DBInstances'][0]['Endpoint']['Port']
        print(f"RDS instance details: {end_point} {port}")
        return end_point,port
    except Exception as e:
        print(f"Error getting RDS instance details: {e}")
        return None
        
def get_db_cluster_endpoint(rds,cluster_identifier):
    try:
        response = rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
        end_point = response['DBClusters'][0]['Endpoint']
        port = response['DBClusters'][0]['Port']
        print(f"DB cluster endpoint details: {end_point} {port}")
        return end_point,port
    except Exception as e:
        print(f"Error getting RDS instance details: {e}")
        return None

def connect_to_rds(host: str, user: str, password: str, port: int) -> mysql.Connection:
    """
    Create a connection to the RDS instance
    """
    if not all([host, user, password]):
        raise ValueError("Host, user, and password are required")

    try:
        print(f"\nAttempting to connect to {host}:{port} as {user}...")
        connection = mysql.connect(
            host=host,
            user=user,
            password=password,
            port=port,
            charset='utf8mb4',
            cursorclass=mysql.cursors.DictCursor,
            ssl=_mysql_ssl_args(),
        )
        print("Successfully connected to the database")
        return connection
    except mysql.Error as e:
        error_code = e.args[0]
        error_message = e.args[1] if len(e.args) > 1 else str(e)
        print(f"Failed to connect to database: Error {error_code}: {error_message}")
        raise
    except Exception as e:
        print(f"Unexpected error while connecting to database: {str(e)}")
        raise

def get_mysql_version(connection: mysql.Connection) -> Dict[str, str]:
    """Get MySQL version information"""
    version_info = {}
    with connection.cursor() as cursor:
        # Get version string
        cursor.execute("SELECT VERSION() as version")
        version_info['version'] = cursor.fetchone()['version']
        
        # Get additional version variables
        version_variables = [
            'innodb_version',
            'protocol_version',
            'version_comment',
            'version_compile_os'
        ]
        for var in version_variables:
            cursor.execute(f"SHOW VARIABLES LIKE %s ",(var,))
            result = cursor.fetchone()
            if result:
                version_info[result['Variable_name']] = result['Value']
    
    return version_info

def determine_database_type(connection: mysql.Connection) -> str:
    try:
        cursor = connection.cursor()
        
        # Initialize type as unknown
        db_type = "Standard"
        
        # Step 1: Check version comment for Aurora or RDS
        cursor.execute("SELECT @@version_comment as version_comment")
        version_comment = cursor.fetchone()['version_comment'].lower()
        
        # Check for RDS in version comment
        if 'rds' in version_comment:
            db_type = "RDS"
            return db_type
        
        #   Aurora-specific function
        try:
            cursor.execute("SELECT AURORA_VERSION() as aurora_version")
            result = cursor.fetchone()
            if result and 'aurora_version' in result and result['aurora_version']:
                db_type = "Aurora"
                print(f"Aurora detected via AURORA_VERSION(): {result['aurora_version']}")
                return db_type
        except Exception:
            pass  # Expected on non-Aurora instances
        
        # If we've reached this point, it's a standard MySQL instance
        return db_type
    except Exception as e:
        print(f"Error determining database type: {str(e)}")
        return "Unknown"
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()

def check_server_upgrade(host: str, user: str, password: str, port: int) -> Dict:
    """
    Run MySQL Shell's util.checkForServerUpgrade using direct command
    """
    try:        
        # MySQL Shell command
        mysqlsh = shlex.quote('mysqlsh')
        safe_user = shlex.quote(user)
        safe_host = shlex.quote(host)
        safe_port = str(port) 
        encoded_password = urllib.parse.quote(password, safe='')

        #command = f"{mysqlsh} --json --no-wizard {user}:{encoded_password}@{host}:{port} -- util checkForServerUpgrade"
        # Enforce TLS for the MySQL Shell connection. Use VERIFY_CA when the RDS
        # global CA bundle is available, otherwise require an encrypted channel.
        ca_path = os.environ.get("RDS_CA_BUNDLE", "/etc/ssl/certs/rds-global-bundle.pem")
        if os.path.exists(ca_path):
            ssl_flags = ["--ssl-mode=VERIFY_CA", f"--ssl-ca={ca_path}"]
        else:
            ssl_flags = ["--ssl-mode=REQUIRED"]

        command = [
            mysqlsh,
            "--json",
            "--no-wizard",
            shlex.quote(f"{safe_user}:{encoded_password}@{safe_host}:{safe_port}"),
            *ssl_flags,
            "--",
            "util",
            "checkForServerUpgrade"
        ]
        safe_command_log = command.copy()
        safe_command_log[3] = "[REDACTED]"
        print(f"\nExecuting command: {safe_command_log}")  
        
        # Execute command
        try:
            process = subprocess.run(  # nosec B603 # Using validated inputs
                command,
                shell=False,
                capture_output=True,
                text=True,
                timeout=300  # 5-minute timeout

            )
            
        
            if process.returncode == 0:
                return {
                    'status': True,
                    'output': process.stdout,
                    'error': None
                }
            else:
                return {
                    'status': False,
                    'error': 'Command failed',
                    'output': process.stderr
                }
        except subprocess.TimeoutExpired:
                return {
                    'status': False,
                    'error': 'Command timed out'
                }
        except subprocess.SubprocessError as e:
            return {
                'status': False,
                'error': f'Subprocess error: {str(e)}'
            }       
    except Exception as e:
        return {
            'status': False,
            'error': str(e)
        }




def get_database_sizes(connection: mysql.Connection, database: str) -> Dict[str, float]:
    """Get size information for a specific database"""
    size_info = {}
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as total_size_mb,
                ROUND(SUM(data_length) / 1024 / 1024, 2) as data_size_mb,
                ROUND(SUM(index_length) / 1024 / 1024, 2) as index_size_mb,
                COUNT(*) as tables_count
            FROM information_schema.tables
            WHERE table_schema = %s
        """, (database,))
        result = cursor.fetchone()
        if result:
            size_info = {
                'total_size_mb': float(result['total_size_mb'] or 0),
                'data_size_mb': float(result['data_size_mb'] or 0),
                'index_size_mb': float(result['index_size_mb'] or 0),
                'tables_count': int(result['tables_count'])
            }
    return size_info

def check_mysql_57_to_80_compatibility(connection: mysql.Connection) -> Dict[str, List[str]]:
    """
    Check MySQL 5.7 to 8.0 upgrade compatibility requirements
    """
    results = {
        'non_compliant': [],
        'warnings': [],
        'compliant': []
    }
    
    try:
        with connection.cursor() as cursor:

            # MySQL Specific
            # Check 1: Integer Display Width Deprecation
            cursor.execute("""
                            SELECT 
                            c.TABLE_SCHEMA as 'Database', 
                            c.TABLE_NAME as 'Table',
                            GROUP_CONCAT(c.COLUMN_NAME,' ',c.COLUMN_TYPE) as 'Columns'    
                            FROM 
                            INFORMATION_SCHEMA.COLUMNS c
                            JOIN INFORMATION_SCHEMA.TABLES t 
                            ON c.TABLE_SCHEMA = t.TABLE_SCHEMA 
                            AND c.TABLE_NAME = t.TABLE_NAME
                            WHERE 
                            c.TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')    
                            AND t.TABLE_TYPE = 'BASE TABLE'
                            AND (         
                            c.COLUMN_TYPE LIKE 'int(%'        
                            OR c.COLUMN_TYPE LIKE 'tinyint(%'        
                            OR c.COLUMN_TYPE LIKE 'smallint(%'        
                            OR c.COLUMN_TYPE LIKE 'mediumint(%'         
                            OR c.COLUMN_TYPE LIKE 'bigint(%' 
                            OR c.COLUMN_TYPE LIKE 'year(%'
                            ) 
                            GROUP BY 
                            c.TABLE_SCHEMA,
                            c.TABLE_NAME

             """)
            int_display_width_results = cursor.fetchall()
            if int_display_width_results:
                results['non_compliant'].append({
                    'check_name': 'Identifies columns using deprecated integer display width syntax',
                    'details': f"Found {len(int_display_width_results)} tables using deprecated integer display width syntax",
                    'specific_details': [
                        {  
                            row['Table'],
                            row['Columns']

                        } for row in int_display_width_results
                    ]
                })
            # Check 2: ZEROFILL Attribute Usage
            cursor.execute("""
                SELECT 
                    TABLE_SCHEMA as 'Database',
                    TABLE_NAME as 'Table',
                    COLUMN_NAME as 'Column',
                    COLUMN_TYPE as 'DataType'
                FROM 
                    INFORMATION_SCHEMA.COLUMNS 
                WHERE 
                    TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
                    AND COLUMN_TYPE LIKE '%zerofill%'
            """)
            zerofill_results = cursor.fetchall()
            if zerofill_results:
                results['non_compliant'].append({
                    'check_name': 'Identifies columns using deprecated ZEROFILL attribute',
                    'details': f"Found {len(zerofill_results)} columns using deprecated ZEROFILL attribute",
                     'specific_details': [
                        {   
                            row['Table'],
                            row['Column'],
                            row['DataType']

                        } for row in zerofill_results
                    ]
                })

            # Check 3: Charset Usage
            cursor.execute("""
                SELECT 
                    TABLE_SCHEMA as 'Database',
                    CHARACTER_SET_NAME as 'Charset',
                    GROUP_CONCAT(TABLE_NAME,' , ') as 'Table'

                FROM 
                    INFORMATION_SCHEMA.TABLES t
                    JOIN INFORMATION_SCHEMA.COLLATION_CHARACTER_SET_APPLICABILITY csa 
                        ON t.TABLE_COLLATION = csa.COLLATION_NAME
                WHERE 
                    TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
                    AND CHARACTER_SET_NAME in ( 'utf8', 'utf8mb3', 'ucs2', 'macroman', 'macce', 'eucjpms', 'big5', 'dec8', 'cp850', 
                        'hp8', 'swe7', 'ascii', 'keybcs2', 'geostd8', 'latin1', 'cp932')
                GROUP BY TABLE_SCHEMA,CHARACTER_SET_NAME
            """)
            charset_results = cursor.fetchall()
            if charset_results:
                results['non_compliant'].append({
                    'check_name': 'Validates character set usage and compatibility',
                    'details': f"Found {len(charset_results)} deprecated charsets",
                    'specific_details': [
                        {   
                            row['Table'],
                            row['Charset']

                        } for row in charset_results
                    ]
                })
        # Check 4: Non-InnoDB Storage Engines
            cursor.execute("""
                SELECT 
                    TABLE_SCHEMA as 'Database',
                    TABLE_NAME as 'Table',
                    ENGINE as 'Engine'
                FROM 
                    INFORMATION_SCHEMA.TABLES 
                WHERE 
                    TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
                    AND ENGINE NOT IN ('InnoDB')
            """)
            engine_results = cursor.fetchall()
            if engine_results:
                results['non_compliant'].append({
                    'check_name': 'Identifies tables using non-InnoDB storage enginess',
                    'details': f"Found {len(engine_results)} tables using non-InnoDB storage engines",
                    'specific_details': [
                        {   
                            row['Table'],
                            row['Engine']

                        } for row in engine_results
                    ]
                })

        # Check 5: Deprecated Authentication Plugins
            cursor.execute("""
                SELECT 
                    user as 'User',
                    plugin as 'AuthPlugin'
                FROM 
                    mysql.user 
                WHERE 
                    plugin = 'mysql_native_password'
            """)
            auth_results = cursor.fetchall()
            if auth_results:
                results['non_compliant'].append({
                    'check_name': 'Identifies use of deprecated authentication plugins',
                    'details': f"Found {len(auth_results)} users using deprecated mysql_native_password plugin",
                    'specific_details':
                    [
                        {
                         row['User'],
                         row['AuthPlugin']
                        } for row in  auth_results
                    ] 
                })
        # Check 6: Deprecated SQL Modes
            var_mode='sql_mode'
            cursor.execute(f"SHOW VARIABLES LIKE %s ",(var_mode,))
            sql_mode = cursor.fetchone()['Value']
            deprecated_modes = ['NO_ZERO_DATE', 'NO_ZERO_IN_DATE']
            used_deprecated_modes = [mode for mode in deprecated_modes if mode in sql_mode]
            if used_deprecated_modes:
                results['non_compliant'].append({
                    'check_name': 'Identifies deprecated SQL modes in use',
                    'details': f"Found deprecated SQL modes in use",
                    'deprecated_modes': used_deprecated_modes
                })
        # Check 7: Tables without Primary Keys
            cursor.execute("""
                    SELECT 
                        t.TABLE_SCHEMA as 'Database',
                        t.TABLE_NAME as 'Table'
                    FROM 
                        INFORMATION_SCHEMA.TABLES t
                        LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                            ON t.TABLE_SCHEMA = tc.TABLE_SCHEMA
                            AND t.TABLE_NAME = tc.TABLE_NAME
                            AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    WHERE 
                        t.TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
                        AND t.TABLE_TYPE = 'BASE TABLE'
                        AND tc.CONSTRAINT_TYPE IS NULL
                """)
            no_pk_results = cursor.fetchall()
            if no_pk_results:
                results['non_compliant'].append({
                    'check_name': 'Identifies tables missing primary keys',
                    'details': f"Found {len(no_pk_results)} tables without primary keys",
                    'specific_details':
                        [
                        {
                          row['Table']  

                        } for row in no_pk_results
                        ] 
                })
        #Check 8: Query to check for tables/columns using MySQL 8.0 reserved words
            reserved_words_check_query = """
            SELECT 
                TABLE_SCHEMA as 'Database',
                TABLE_NAME as 'Table',
                COLUMN_NAME as 'Column'
            FROM 
                INFORMATION_SCHEMA.COLUMNS
            WHERE 
                TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
                AND (
                    UPPER(TABLE_NAME) IN (
                        'CLONE', 'COMPONENT', 'CUME_DIST', 
                        'DENSE_RANK', 'EMPTY', 'EXCEPT', 
                        'FIRST_VALUE', 'FUNCTION', 'GROUPING', 
                        'GROUPS', 'JSON_TABLE', 'LAG', 
                        'LAST_VALUE', 'LEAD', 'NTH_VALUE', 
                        'NTILE', 'OF', 'OVER', 
                        'PERCENT_RANK', 'PERSIST', 'PERSIST_ONLY', 
                        'RANK', 'RECURSIVE', 'ROW_NUMBER', 
                        'SYSTEM', 'WINDOW'
                    )
                    OR 
                    UPPER(COLUMN_NAME) IN (
                        'CLONE', 'COMPONENT', 'CUME_DIST', 
                        'DENSE_RANK', 'EMPTY', 'EXCEPT', 
                        'FIRST_VALUE', 'FUNCTION', 'GROUPING', 
                        'GROUPS', 'JSON_TABLE', 'LAG', 
                        'LAST_VALUE', 'LEAD', 'NTH_VALUE', 
                        'NTILE', 'OF', 'OVER', 
                        'PERCENT_RANK', 'PERSIST', 'PERSIST_ONLY', 
                        'RANK', 'RECURSIVE', 'ROW_NUMBER', 
                        'SYSTEM', 'WINDOW'
                    )
                );
            """
            cursor.execute(reserved_words_check_query)
            reserved_word_issues = cursor.fetchall()
            if reserved_word_issues:
                results['non_compliant'].append({
                    'check_name': 'Identifies usage of MySQL 8.0 reserved words in table/column names',
                    'details': f"Reserved word conflict found  {len(reserved_word_issues)} ",
                    'specific_details': [

                        {
                            row['Table'],
                            row['Column']
                        } for row in reserved_word_issues
                    ] 
                })
            #check 9 Temporal issues
            temporal_issues = """
                            SELECT 
                                CASE 
                                    WHEN COLUMN_DEFAULT IN ('0000-00-00', '0000-00-00 00:00:00') 
                                        THEN 'Zero date default'
                                    WHEN DATA_TYPE IN ('timestamp', 'datetime') 
                                        AND COLUMN_DEFAULT IS NULL 
                                        AND IS_NULLABLE = 'NO' 
                                        AND EXTRA NOT LIKE '%CURRENT_TIMESTAMP%' 
                                        THEN 'Non-nullable without default'
                                    WHEN DATA_TYPE = 'timestamp' 
                                        AND IS_NULLABLE = 'NO' 
                                        AND EXTRA NOT LIKE '%CURRENT_TIMESTAMP%' 
                                        THEN 'Timestamp without CURRENT_TIMESTAMP'
                                    ELSE 'Other temporal issue'
                                END as 'Issue',
                                COUNT(DISTINCT CONCAT(TABLE_SCHEMA, '.', TABLE_NAME)) as 'NoOfTables',
                                COUNT(*) as 'NoOfColumns'

                            FROM 
                                INFORMATION_SCHEMA.COLUMNS
                            WHERE 
                                TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
                                AND DATA_TYPE IN ('date', 'datetime', 'timestamp')
                                AND (
                                    COLUMN_DEFAULT IN ('0000-00-00', '0000-00-00 00:00:00')
                                    OR (DATA_TYPE IN ('timestamp', 'datetime') 
                                        AND COLUMN_DEFAULT IS NULL 
                                        AND IS_NULLABLE = 'NO' 
                                        AND EXTRA NOT LIKE '%CURRENT_TIMESTAMP%')
                                    OR (DATA_TYPE = 'timestamp' 
                                        AND IS_NULLABLE = 'NO' 
                                        AND EXTRA NOT LIKE '%CURRENT_TIMESTAMP%')
                                )
                            GROUP BY 
                                CASE 
                                    WHEN COLUMN_DEFAULT IN ('0000-00-00', '0000-00-00 00:00:00') 
                                        THEN 'Zero date default'
                                    WHEN DATA_TYPE IN ('timestamp', 'datetime') 
                                        AND COLUMN_DEFAULT IS NULL 
                                        AND IS_NULLABLE = 'NO' 
                                        AND EXTRA NOT LIKE '%CURRENT_TIMESTAMP%' 
                                        THEN 'Non-nullable without default'
                                    WHEN DATA_TYPE = 'timestamp' 
                                        AND IS_NULLABLE = 'NO' 
                                        AND EXTRA NOT LIKE '%CURRENT_TIMESTAMP%' 
                                        THEN 'Timestamp without CURRENT_TIMESTAMP'
                                    ELSE 'Other temporal issue'
                                END
                            ORDER BY 
                                Column_Count DESC;

            """
            cursor.execute(temporal_issues)
            temporal_issues = cursor.fetchall()
            if temporal_issues:
                results['non_compliant'].append({
                    'check_name': 'Validates temporal data type usage',
                    'details': f"Temporal issues found  {len(temporal_issues)}  ",
                    'specific_details':[{
                        row['Issue'],
                        'No.Of.Tables:', row['NoOfTables'] ,
                        'No.Of.Columns:',row['NoOfColumns']   
                    } for row in temporal_issues
                    ] 
                })


            #Check 10- Potential Behavior Changes in JSON Functions
            json_behaviour_changes = """

                                SELECT 
                                o.object_schema as Database,
                                Count(o.object_name)  as StoredObject, 
                                    GROUP_CONCAT(CASE 
                                        WHEN o.sql_text LIKE '%JSON_EXTRACT%' THEN 'JSON_EXTRACT'
                                        WHEN o.sql_text LIKE '%JSON_CONTAINS%' THEN 'JSON_CONTAINS'
                                        WHEN o.sql_text LIKE '%JSON_SEARCH%' THEN 'JSON_SEARCH'
                                        WHEN o.sql_text LIKE '%JSON_ARRAY%' THEN 'JSON_ARRAY'
                                        WHEN o.sql_text LIKE '%JSON_OBJECT%' THEN 'JSON_OBJECT'
                                        WHEN o.sql_text LIKE '%->%' THEN 'JSON_PATH_OPERATOR'
                                        WHEN o.sql_text LIKE '%->>%' THEN 'JSON_INLINE_PATH'
                                        ELSE 'OTHER_JSON_FUNCTION'
                                    END ) as JSON_Functions

                                FROM (
                                SELECT 
                                ROUTINE_TYPE as object_type,
                                ROUTINE_SCHEMA as object_schema,
                                ROUTINE_NAME as object_name,
                                ROUTINE_DEFINITION as sql_text
                                FROM INFORMATION_SCHEMA.ROUTINES
                                WHERE (ROUTINE_DEFINITION REGEXP 'JSON_[A-Z]+'
                                OR ROUTINE_DEFINITION LIKE '%->%'
                                OR ROUTINE_DEFINITION LIKE '%->>%')
                                AND ROUTINE_SCHEMA NOT IN ('mysql', 'sys', 'information_schema', 'performance_schema')
                                UNION ALL
                                SELECT 
                                'VIEW' as object_type,
                                TABLE_SCHEMA as object_schema,
                                TABLE_NAME as object_name,
                                VIEW_DEFINITION as sql_text
                                FROM INFORMATION_SCHEMA.VIEWS
                                WHERE VIEW_DEFINITION REGEXP 'JSON_[A-Z]+'
                                OR VIEW_DEFINITION LIKE '%->%'
                                OR VIEW_DEFINITION LIKE '%->>%'
                                UNION ALL
                                SELECT 
                                'TRIGGER' as object_type,
                                TRIGGER_SCHEMA as object_schema,
                                TRIGGER_NAME as object_name,
                                ACTION_STATEMENT as sql_text
                                FROM INFORMATION_SCHEMA.TRIGGERS
                                WHERE ACTION_STATEMENT REGEXP 'JSON_[A-Z]+'
                                OR ACTION_STATEMENT LIKE '%->%'
                                OR ACTION_STATEMENT LIKE '%->>%'
                                ) o
                                WHERE 
                                o.sql_text REGEXP 'JSON_(EXTRACT|CONTAINS|SEARCH|ARRAY|OBJECT|TYPE)'
                                OR o.sql_text LIKE '%->%'
                                OR o.sql_text LIKE '%->>%'
                                OR o.sql_text LIKE '%JSON_%NULL%'
                                OR o.sql_text LIKE '%JSON_%[%'
                                group by object_schema
            """
            cursor.execute(json_behaviour_changes)
            json_behaviour_changes = cursor.fetchall()
            if json_behaviour_changes:
                results['non_compliant'].append({
                    'check_name': 'Identifies potential JSON function behavior changes',
                    'details': f"JSON functions used  {len(temporal_issues)}  ",
                    'specific_details': [{
                    'Stored Object Name:',row['StoredObject'],
                    'JSON Functions Used:',row['JSON_Functions']

                    } for row in json_behaviour_changes
                    ]
                })

            # If no non-compliant items were found in mysql_specific section
            if not results['non_compliant']:
                results['compliant'].append({
                    'check_name': 'MySQL Deprecated Features',
                    'details': 'No deprecated features or unsupported configurations found',
                    'specific_details' :''
                })


            # Add compliance messages if no issues found
            if not results['non_compliant'] and not results['warnings']:
                results['compliant'].append("All MySQL 5.7 to 8.0 upgrade compatibility checks passed")

    except mysql.Error as e:
        results['warnings'].append(f"Error during compatibility check: {str(e)}")

    return results


def check_rds_specific_requirements(connection: mysql.Connection, region: str, cluster_instance_id: str) -> Dict:
    """Check RDS/Aurora specific requirements for upgrade"""
    rds_checks = {
        'instance_checks': [],
        'mysql_specific': {
            'compliant': [],
            'non_compliant': [],
            'warnings'  :[]
        },
        'parameter_group': {
            'compliant': [],
            'non_compliant': []
        },
        'storage': {
            'compliant': [],
            'non_compliant': []
        },
        'backup': []
    }
    
    cursor = connection.cursor()
    try:

        # Determine database type
        db_type = determine_database_type(connection)

        # Check if it's not an AWS managed database
        if db_type == "Standard":
            rds_checks['instance_checks'].append("WARNING: This doesn't appear to be an RDS or Aurora instance"
        )
        else:
            rds_checks['instance_checks'].append(f"{db_type}")
            print("\nChecking MySQL 5.7 to 8.0 upgrade compatibility...")
            upgrade_checks = check_mysql_57_to_80_compatibility(connection)
            rds_checks['mysql_specific']['non_compliant'].extend(upgrade_checks['non_compliant'])
            rds_checks['mysql_specific']['warnings'].extend(upgrade_checks['warnings'])
            rds_checks['mysql_specific']['compliant'].extend(upgrade_checks['compliant'])


    # Storage Checks
        try:
            print('Code Enhancement')
        except mysql.Error as e:
            rds_checks['storage']['non_compliant'].append(
                f"Error checking storage requirements: {str(e)}"
            )
        # Backup Checks
        cursor = connection.cursor()
        try:
            # Check backup settings
            backup_settings = check_backup_settings(connection, region, cluster_instance_id)
            rds_checks['backup'] = backup_settings['backup_status']
            rds_checks['backup_flag'] = backup_settings['backup_status_flag']
            return rds_checks
        except mysql.Error as e:
            rds_checks['backup'].append(
                f"Error checking backup retention period: {str(e)}"
            )

        # Parameter Group Checks 
        required_parameters = {
            'binlog_format': {'expected': 'ROW', 'description': 'Binary log format'}
        }

        for param, requirements in required_parameters.items():
            try:
                cursor.execute("SELECT @@%s AS value", (param,))
                result = cursor.fetchone()
                if result:
                    current_value = str(result['value']).upper()
                    expected_value = requirements['expected']
                    
                    if not isinstance(expected_value, tuple):
                        expected_value = (expected_value,)
                    
                    if current_value in [str(v).upper() for v in expected_value]:
                        rds_checks['parameter_group']['compliant'].append(
                            f"{requirements['description']} ({param}) is correctly set to: {current_value}"
                        )
                    else:
                        rds_checks['parameter_group']['non_compliant'].append(
                            f"{requirements['description']} ({param}) should be {expected_value[0]} (current: {current_value})"
                        )
            except mysql.Error as e:
                rds_checks['parameter_group']['non_compliant'].append(
                    f"Could not verify {param}: {str(e)}"
                )
        # Instance Checks
        cursor.execute("SELECT @@read_only as readonly")
        read_only = cursor.fetchone()['readonly']
        if read_only:
            rds_checks['instance_checks'].append(
                "Instance is read-only (replica). Primary instance required for upgrade"
            )
        else:
            rds_checks['instance_checks'].append(
                "Instance is not in read-only mode (primary instance)"
            )

        return rds_checks

    except mysql.Error as e:
        print(f"Error in RDS checks: {str(e)}")
        rds_checks['instance_checks'].append(f"Error performing checks: {str(e)}")
        return rds_checks
    finally:
        cursor.close()


def check_backup_settings(connection: mysql.Connection, region: str, cluster_instance_id: str) -> Dict:
    """
    Check backup settings and latest snapshot status for RDS/Aurora
    """
    backup_settings = {
        'environment': '',
        'backup_status': [],
        'backup_status_flag': []
    }

    try:
        # Use get_mysql_version function to get version information
        version_info = get_mysql_version(connection)
        mysql_version = version_info['version']
        version_comment = version_info.get('version_comment', '').lower()
        rds_client = boto3.client('rds', region_name=region)
        # Get all snapshots for the specified DB instance
        response = rds_client.describe_db_snapshots(
            DBInstanceIdentifier=cluster_instance_id,
            SnapshotType='manual'
        )
        if   response['DBSnapshots']:
            # Initialize variables to track latest snapshot
            latest_snapshot = None
            latest_time = None
            # Iterate through snapshots to find the latest one
            for snapshot in response['DBSnapshots']:
                snapshot_time = snapshot['SnapshotCreateTime']
                # Get snapshot details
                if latest_time is None or snapshot_time > latest_time:
                    latest_time = snapshot_time
                    latest_snapshot = snapshot

            snapshot_id = latest_snapshot['DBSnapshotIdentifier']
            snapshot_time = latest_snapshot['SnapshotCreateTime']
            # Convert to UTC for comparison
            current_time = datetime.now(timezone.utc)
            # Check if the snapshot was taken today
            is_today = snapshot_time.date() == current_time.date()

            # Print snapshot details
            print(f"\nLatest snapshot details:")
            print(f"Snapshot ID: {snapshot_id}")
            print(f"Creation Time: {snapshot_time}")
            print(f"Snapshot taken today: {is_today}")
            
            # Additional details that might be useful
            '''
            print(f"Snapshot Status: {latest_snapshot['Status']}")
            print(f"Snapshot Type: {latest_snapshot['SnapshotType']}")
            print(f"Engine: {latest_snapshot['Engine']}")
            print(f"Engine Version: {latest_snapshot['EngineVersion']}")
            '''
            if is_today:
                backup_settings['backup_status'].append(
                            f"Latest snapshot taken today at {snapshot_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                backup_settings['backup_status_flag'].append(1)
            else:

                backup_settings['backup_status'].append(
                            f"Latest snapshot was from {snapshot_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                backup_settings['backup_status_flag'].append(2)

        else:
            print(f"No snapshots found for DB instance {cluster_instance_id}")
            backup_settings['backup_status'].append("No snapshots found")
            backup_settings['backup_status_flag'].append(3)

        # Determine database type
        db_type = determine_database_type(connection)        
        # Check if it's not an AWS managed database
        if db_type == "Standard":
            backup_settings['backup_status'].append(f"Running on standard MySQL {mysql_version}")
        else:
            backup_settings['environment'] =db_type



    except Exception as e:
        backup_settings['backup_status'].append(f"Unexpected error: {str(e)}")

    return backup_settings

def check_custom_option_group(connection: mysql.Connection, region: str, cluster_instance_id: str) -> Dict:
    """
    Check if RDS/Aurora MySQL instance uses a custom option group
    
    Args:
        rds_client: Boto3 RDS client
        cluster_instance_id: RDS instance identifier
        
    Returns:
        Dict containing custom option group check results
    """
    result = {
        'compliant': True,
        'custom_option_group': False,
        'option_group_name': None,
        'message': '',
        'recommendation': ''
    }

    try:
        rds_client = boto3.client('rds', region_name=region)
        #print("check_custom_option_group cluster_instance_id ",cluster_instance_id)
        response = rds_client.describe_db_instances(
            DBInstanceIdentifier=cluster_instance_id
        )
        #print("check_custom_option_group: response ",response)
        if not response['DBInstances']:
            result['compliant'] = False
            result['message'] = f"No instance found with identifier {cluster_instance_id}"
            return result

        instance = response['DBInstances'][0]
        option_groups = instance['OptionGroupMemberships']
        
        for option_group in option_groups:
            option_group_name = option_group['OptionGroupName']
            result['option_group_name'] = option_group_name
            
            # Check if option group is custom (not default)
            if not option_group_name.startswith('default:'):
                result['custom_option_group'] = True
                result['compliant'] = False
                result['message'] = (
                    f"Instance uses custom option group '{option_group_name}'. "
                    "Major version upgrade during blue/green deployment is not supported."
                )
            else:
                result['compliant'] = True
                result['message'] = f"Instance uses default option group '{option_group_name}'"

    except ClientError as e:
        result['compliant'] = False
        result['message'] = f"Error checking option groups: {str(e)}"
        
    return result



def check_rds_version_compatibility(connection: mysql.Connection) -> Dict:
    """Check RDS/Aurora version compatibility for 8.0 upgrade"""
    compatibility = {
        'status': True,
        'issues': []
    }
    
    cursor = connection.cursor()
    try:
        # Check current version
        cursor.execute("SELECT @@version as version")
        version = cursor.fetchone()['version']
        
        # Check if version is compatible
        if not version.startswith('5.7'):
            compatibility['status'] = False
            compatibility['issues'].append(
                f"Current version {version} is not 5.7. Only 5.7 can be upgraded to 8.0"
            )
        
        # Check minimum version requirement
        if version < '5.7.23':
            compatibility['status'] = False
            compatibility['issues'].append(
                f"Version {version} is below minimum required version 5.7.23"
            )
            
        return compatibility
        
    finally:
        cursor.close()

def check_secrets_manager_status(connection: mysql.Connection, region: str, cluster_instance_id: str)  -> bool:
    try:
        #print("inside check_secrets_manager_status ")
        rds_client = boto3.client('rds', region_name=region)
        #print("inside check_secrets_manager_status :1  ")
        response = rds_client.describe_db_instances(
            DBInstanceIdentifier=cluster_instance_id
        )
        #print("inside check_secrets_manager_status :2  ")
        instance = response['DBInstances'][0]
        #print("check_secrets_manager_status response['DBInstances'][0]",response['DBInstances'][0])
        secret_manager_enabled = instance.get('MasterUserSecret', False)
        if secret_manager_enabled:
            return True
        else:
            return False 
        
    except ClientError as e:
            return False

def check_rds_blue_green_limitations(connection: mysql.Connection,cluster_instance_id,region) -> Dict:
    try:

        limitations = {
                        'general_limitations': 
                        {
                        'compliant': [],
                        'non_compliant': []
                        },
                        'mysql_specific': 
                        {
                        'compliant': [],
                        'non_compliant': []
                        },
                        'recommendations': []
                    }
        #print("check_rds_blue_green_limitations: 1 ")        
        # 1. Check if instance is an external binlog replica
        with connection.cursor() as cursor:
            cursor.execute("SHOW SLAVE STATUS")
            slave_status = cursor.fetchone()
            if slave_status:
                master_host = slave_status.get('Master_Host', '')
                if not any(x in master_host.lower() for x in ['.rds.amazonaws.com', '.rds.internal']):
                    limitations['mysql_specific']['non_compliant'].append(
                        "The blue DB instance cannot be an external binlog replica"
                    )
                else:
                    limitations['mysql_specific']['compliant'].append(
                        "DB instance is not configured as an external binlog replica"
                    )
        #print("check_rds_blue_green_limitations: 2 ")        

        # 2. Check for custom option groups with major version upgrade
        #print("option_group_check before")

        option_group_check = check_custom_option_group(connection, region, cluster_instance_id)
        #print("option_group_check after")

        if option_group_check['compliant']:
            limitations['general_limitations']['compliant'].append(
                option_group_check['message']
            )
        else:
            limitations['general_limitations']['non_compliant'].append(
                option_group_check['message']
            )
            if option_group_check['recommendation']:
                limitations['recommendations'].append(
                    option_group_check['recommendation']
                )
        # 3. Check for AWS JDBC Driver for MySQL usage
        #print("check_rds_blue_green_limitations: 3 ")  
        with connection.cursor() as cursor:
            cursor.execute("SHOW PROCESSLIST")
            processes = cursor.fetchall()
            jdbc_connections = [p for p in processes if 'aws.jdbc.driver' in str(p.get('Info', '')).lower()]
            if jdbc_connections:
                limitations['general_limitations']['non_compliant'].append(
                    "The AWS JDBC Driver for MySQL is not supported for blue/green deployments"
                )
            else:
                limitations['general_limitations']['compliant'].append(
                    "No AWS JDBC Driver for MySQL connections detected"
                )
        #print("check_rds_blue_green_limitations: 4 ")  
        # 4. Check for Secrets Manager
        secret_manager_status = check_secrets_manager_status(connection,region,cluster_instance_id)
        #print("check_rds_blue_green_limitations: 4.1 ") 
        if secret_manager_status:
            #print("check_rds_blue_green_limitations - Secret Manager enabled")
            limitations['general_limitations']['non_compliant'].append(
                "Blue/green deployments don't support managing master user passwords with AWS Secrets Manager"
            )
        else:   
            #print("check_rds_blue_green_limitations - Secret Manager Not enabled")
            limitations['general_limitations']['compliant'].append("Secrets Manager not enabled")
        #print("check_rds_blue_green_limitations: 5 ")  
        # Comprehensive Recommendations
        ''' 
        limitations['recommendations'].extend([
                "1. Pre-deployment Requirements:",
                "   - Ensure no databases are named with 'tmp' prefix",
                "   - Ensure instance is not a replica",
                "   - For Aurora: be aware that backtrack will not be supported in green environment",
                "   - Convert all tables to InnoDB engine",
                "   - Set binary log format to ROW",
                "",
                "2. Review and Document:",
                "   - All database triggers",
                "   - All foreign key relationships",
                "   - Current configuration settings",
                "",
                "3. During Deployment:",
                "   - Ensure no schema changes during switchover",
                "   - Monitor replication lag",
                "   - Have rollback plan ready",
                "   - Prepare for brief application read-only period",
                "",
                "4. Application Considerations:",
                "   - Implement connection retry logic",
                "   - Test application with read-only database",
                "   - Plan for temporary performance impact",
                "",
                "5. Post-deployment Tasks:",
                "   - Verify all triggers functionality",
                "   - Validate all foreign key constraints",
                "   - Monitor performance metrics",
                "   - Test application functionality"
            ])
        '''
        
        return limitations
    except Exception as e:
        print(f"\nError in check_rds_blue_green_limitations: {str(e)}")
        traceback.print_exc()
        return limitations
 

def generate_html_report(databases_info: List[Dict], mysql_version: Dict[str, str], 
                        rds_checks: Dict, version_compatibility: Dict, 
                        blue_green_limitations: Dict, upgrade_check_results: Dict,
                        cluster_instance_id: str,bucket: str) -> str:
    """
    Generate a single HTML report for all databases
    """
    filename = f"{cluster_instance_id}-precheck-report.html"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>MySQL Upgrade Pre-check Report</title>
       <style>
         

        :root {{
        --aws-blue: #232f3e;
        --aws-light-blue: #0073bb;
        --aws-bg-gray: #f2f3f3;
        --aws-border-gray: #d5dbdb;
        --aws-text-primary: #16191f;
        --aws-success-green: #1d8102;
        --aws-warning-red: #d13212;
        --aws-warning-bg: #fdf3f1;
        --aws-warning-border: #f1b4a4;
        }}
    body {{
        font-family: "Amazon Ember", Arial, sans-serif;
        line-height: 1.6;
        margin: 20px;
        background-color: var(--aws-bg-gray);
    }}
    .container {{
        max-width: 1200px;
        margin: 0 auto;
        background-color: white;
        padding: 20px;
        border-radius: 5px;
        box-shadow: 0 1px 1px 0 rgba(0,28,36,0.3);
    }}
    h1 {{
        color: #f5b60a;
        border-bottom: 2px solid #232f3e;
        padding-bottom: 10px;
    }}
    h2 {{
        color: #0c97e8;
        margin-top: 20px;
    }}
    h3 {{
        color: #e38f56;
        margin-bottom: 15px;
    }}
    h4 {{
        color: #6e43c4;
        margin-bottom: 15px;
    }}
    .section {{
        margin: 20px 0;
        padding: 15px;
        border: 1px solid #d5dbdb;
        border-radius: 5px;
    }}
    .subsection {{
        margin: 20px 0;
        padding: 20px;
        border: 1px solid #d5dbdb;
        border-radius: 5px;
        background-color: #fff;
    }}
    .warning {{
        color: #d13212;
        background-color: #fdf3f1;
        border: 1px solid #f1b4a4;
        padding: 10px;
        margin: 10px 0;
        border-radius: 4px;
    }}
    .check-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 10px 0;
    }}
    .check-table th, .check-table td {{
        border: 1px solid #d5dbdb;
        padding: 12px;
        text-align: left;
    }}
    .check-table th {{
        background-color: #fafafa;
        font-weight: bold;
        color: #16191f;
    }}
    .success {{
        color: #1d8102;
    }}
    .status-cell {{
        text-align: center;
        vertical-align: middle;
        width: 5%;
    }}
    .radio-button {{
        color: #d13212;
        font-size: 20px;
        display: inline-block;
        line-height: 1;
    }}
    .details-pre {{
        white-space: pre-wrap;
        word-wrap: break-word;
        background-color: #f8f9fa;
        padding: 8px;
        margin: 0;
        border-radius: 4px;
        font-size: 13px;
        border: 1px solid #d5dbdb;
    }}
    .success-icon {{
        color: #1d8102;
        font-weight: bold;
    }}
    .version-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        background-color: #fff;
    }}
    .version-table th {{
        background-color: #fafafa;
        color: #16191f;
        font-weight: bold;
        padding: 12px;
        border: 1px solid #d5dbdb;
        text-align: left;
        width: 30%;
    }}
    .version-table td {{
        padding: 12px;
        border: 1px solid #d5dbdb;
        color: #16191f;
    }}
    .database-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        background-color: #fff;
    }}
    .database-table th {{
        background-color: #fafafa;
        color: #16191f;
        font-weight: bold;
        padding: 12px;
        border: 1px solid #d5dbdb;
        text-align: left;
    }}
    .database-table td {{
        padding: 12px;
        border: 1px solid #d5dbdb;
        color: #16191f;
    }}
    .database-name {{
        font-weight: bold;
        color: #148185;
    }}

    .metric-value {{
        text-align: right;
        font-family: monospace;
    }}
    .summary {{
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 5px;
        margin: 20px 0;
        border: 1px solid #d5dbdb;
    }}
    .ok {{
        color: #1d8102;
        font-weight: bold;
        padding: 10px;
        margin: 10px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .ok::before {{
        content: '✓';
        font-size: 18px;
        line-height: 1;
    }}
    .check-icon {{
        font-size: 18px;
        margin-right: 8px;
        color: #1d8102;
    }}
    .non-compliant {{
        color: #16191f;   
        padding: 8px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .warning-icon {{
        color: #d13212;  
        font-size: 18px;
        line-height: 1;
    }}
    .non-compliant-header {{
        color: #d13212;
        font-weight: bold;
        margin: 15px 0 10px 0;
    }}
    .non-compliant-list {{
        list-style: none;
        padding-left: 0;
        margin: 10px 0;
    }}

    .upgrade-check {{
        margin: 20px 0;
        font-family: "Amazon Ember", Arial, sans-serif;
    }}
    .warning-message {{
        background-color: #fdf3f1;
        border: 1px solid #f1b4a4;
        color: #d13212;
        padding: 12px;
        margin-bottom: 20px;
        border-radius: 4px;
    }}
    .section-title {{
        color: #232f3e;
        margin: 20px 0 10px 0;
        padding-bottom: 5px;
        border-bottom: 2px solid #eee;
    }}
    .info-table {{
        width: 100%;
    }}
    .info-table th {{
        background-color: #fafafa;
        text-align: left;
        padding: 12px 15px;
        border: 1px solid #d5dbdb;
        font-weight: 600;
        color: #16191f;
    }}
    .info-table td {{
        border: 1px solid #d5dbdb;
        color: #16191f;
    }}
    .status-badge {{
        display: inline-block;
        padding: 4px 8px;
        border-radius: 4px;
        margin: 2px 4px;
        font-weight: bold;
    }}
    .error-count {{
        background-color: #fdf3f1; 
        color: #d13212; 
        border: 1px solid #f1b4a4;
    }}
    .warning-count {{
        background-color: #fff4df; 
        color: #c77c02; 
        border: 1px solid #f1b84b;
    }}
    .notice-count {{
        background-color: #eef4ff; 
        color: #0073bb; 
        border: 1px solid #b5d6f4;
    }}
    .check-status {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-weight: bold;
    }}
    .status-ok {{ 
        color: #1d8102;
        background-color: #e6f6ed;
        padding: 4px 8px;
        border-radius: 4px;
    }}
    .status-error {{ 
        color: #d13212;
        background-color: #fdf3f1;
        padding: 4px 8px;
        border-radius: 4px;
    }}
    .status-warning {{ 
        color: #c77c02;
        background-color: #fff4df;
        padding: 4px 8px;
        border-radius: 4px;
    }}
    .check-id {{
        font-family: "Amazon Ember Mono", monospace;
        color: #545b64;
        font-size: 0.9em;
    }}
    .problems-list {{
        margin: 5px 0;
        padding-left: 20px;
    }}
    .problems-list li {{
        margin: 5px 0;
        color: #d13212;
    }}
    .no-problems {{
        color: #1d8102;
        font-style: italic;
    }}
    .check-results th:nth-child(1) {{ width: 15%; }}  /* Check ID */
    .check-results th:nth-child(2) {{ width: 25%; }}  /* Title */
    .check-results th:nth-child(3) {{ width: 10%; }}  /* Status */
    .check-results th:nth-child(4) {{ width: 50%; }}  /* Detected Problems */
</style>

    </head>
    <body>
        <div class="container">
            <h1 style="font-family:verdana" >MySQL Upgrade Pre-check Report</h1>
            <div class="summary">
                <h2>Overview</h2>
                <p>Report Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                <p>Number of Databases: {len(databases_info)}</p>
            </div>
    """
    
    # Add MySQL version information
    html_content += """
    <div class="section">
        <h2>MySQL Version Information</h2>
        <table class="version-table">
            <tr><th>Parameter</th><th>Value</th></tr>
    """
    for key, value in mysql_version.items():
        html_content += f"<tr><td>{key}</td><td>{value}</td></tr>"

    html_content += """
        </table>
    </div>
    """

    # Add Version Compatibility Check
    html_content += """
    <div class="section">
        <h2>Version Compatibility Check</h2>
    """
    if version_compatibility['status']:
        html_content += '<p class="ok">Version is compatible for upgrade</p>'
    else:
        html_content += '<h3>Compatibility Issues:</h3><ul>'
        for issue in version_compatibility['issues']:
            html_content += f'<li class="warning">{issue}</li>'
        html_content += '</ul>'
    html_content += "</div>"

    # Add RDS checks
    html_content += """
    <!-- MySQL 5.7 to 8.0 Upgrade Compatibility Section -->
    <div class="section">
        <h2>MySQL 5.7 to 8.0 Upgrade Compatibility</h2>
        
        <!-- MySQL Specific Checks -->
        <div class="subsection">
            <h3>Compatibility Checks</h3>
            <table class="check-table">
                <thead>
                    <tr>
                        <th width="5%"></th>
                        <th width="25%">Check Name</th>
                        <th width="30%">Details</th>
                        <th width="40%">Specific Details</th>
                    </tr>
                </thead>
                <tbody>
    """
    for check in rds_checks.get('mysql_specific', {}).get('non_compliant', []):
        if isinstance(check, dict):
            html_content += f"""
                <tr>
                    <td class="status-cell">
                        <span class="radio-button">&#9679;</span>
                    </td>
                    <td>{check.get('check_name', 'N/A')}</td>
                    <td>{check.get('details', 'N/A')}</td>
                    <td><pre class="details-pre">{check.get('specific_details', 'N/A')}</pre></td>
                </tr>
            """


    html_content += """
                    </tbody>
                </table>
            <!--  Backup Status -->
                <h3> Backup Status</h3>                
                <!-- Backup Status -->
                <div class="status-section">
                    <table class="check-table">
                        <thead>
                            <tr>
                                <th width="20%">Status</th>
                                <th width="80%">Details</th>
                            </tr>
                        </thead>
                        <tbody>
    """

    for check in rds_checks.get('backup', []):
        
        for check_flag in rds_checks.get('backup_flag', []):
           print("backup_status_flag:check_flag %",check_flag)
        if check_flag == 1:
         color_style = "'background-color: #e6f6ed; color: #1d8102; padding: 8px;'"  
         message = "Latest Backup Available"

        elif check_flag == 2:
            color_style = "'background-color: #fff4df; color: #c77c02; padding: 8px;'"  # Yellow
            message = "Latest Backup Not Available"

        elif check_flag == 3:
            color_style = "'background-color: #fdf3f1; color: #d13212; padding: 8px;'"  # Red
            message = "Backup Not Available"

        html_content += f"""
            <tr>
                <td style={color_style}>{message}</td>
                <td>{check}</td>
            </tr>
        """

    html_content += """
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    """



    # Add Blue/Green Deployment Limitations
    html_content += """
    <div class="section">
        <h2>Blue/Green Deployment Limitations</h2>
    """
    
    # General Limitations
    if blue_green_limitations.get('general_limitations'):
        html_content += "<h3>General Limitations</h3>"
        # Compliant Items
        if blue_green_limitations['general_limitations'].get('compliant'):
            html_content += "<h4>Compliant:</h4><ul>"
            for item in blue_green_limitations['general_limitations']['compliant']:
                html_content += f"""
                    <li class="compliant">
                        <p class="ok"> {item}
                    </li>"""
            html_content += "</ul>"
        
        # Non-Compliant Items
        if blue_green_limitations['general_limitations'].get('non_compliant'):
            html_content += "<h4>Non-Compliant:</h4><ul>"
            for item in blue_green_limitations['general_limitations']['non_compliant']:
                html_content += f"""
                    <li class="non-compliant">
                        <span  class="warning-icon">⚠</span>{item}
                    </li>"""
            html_content += "</ul>"

    # MySQL Specific Limitations
    ''' 
    if blue_green_limitations.get('mysql_specific'):
        html_content += "<h3>MySQL Specific Limitations</h3>"
        
        # Compliant Items
        if blue_green_limitations['mysql_specific'].get('compliant'):
            html_content += "<h4>Compliant:</h4><ul>"
            for item in blue_green_limitations['mysql_specific']['compliant']:
                html_content += f"""
                    <li class="compliant">
                        <span class="ok">✓</span>{item}
                    </li>"""
            html_content += "</ul>"
        
        # Non-Compliant Items
        if blue_green_limitations['mysql_specific'].get('non_compliant'):
            html_content += "<h4>Non-Compliant:</h4><ul>"
            for item in blue_green_limitations['mysql_specific']['non_compliant']:
                html_content += f"""
                    <li class="non-compliant">
                        <span class="check-icon">⚠</span>
                        <span>{item}</span>
                    </li>"""
            html_content += "</ul>"
    '''
    # Recommendations
    ''' 
    if blue_green_limitations.get('recommendations'):
        html_content += """
        <h3>Recommendations</h3>
        <div class="recommendations">
        <ul>"""
        for item in blue_green_limitations['recommendations']:
            if item.startswith(('1.', '2.', '3.', '4.', '5.')):
                # Main category headers
                html_content += f'<li class="category">{item}</li>'
            elif item.startswith('   -'):
                # Sub-items
                html_content += f'<li class="sub-item">{item}</li>'
            elif item.strip() == "":
                # Empty lines for spacing
                html_content += '<li style="height: 10px;"></li>'
            else:
                # Regular items
                html_content += f'<li>{item}</li>'
        html_content += "</ul></div>"
    
    html_content += "</div> </div>"
    
    '''

    html_content += '''
                        </div>
                    '''
    # Add database-specific information
    html_content += """
    <div class="section">
        <h2 >Database Details</h2>
    """

    for db_info in databases_info:
        html_content += f"""
        <div class="subsection">
            <h3 class="database-name">{db_info['database']}</h3>
            <table class="database-table">
                <tr>
                    <th>Metric</th>
                    <th>Value</th>
                </tr>
                <tr>
                    <td>Total Size</td>
                    <td class="metric-value">{db_info['database_sizes']['total_size_mb']:.2f} MB</td>
                </tr>
                <tr>
                    <td>Data Size</td>
                    <td class="metric-value">{db_info['database_sizes']['data_size_mb']:.2f} MB</td>
                </tr>
                <tr>
                    <td>Index Size</td>
                    <td class="metric-value">{db_info['database_sizes']['index_size_mb']:.2f} MB</td>
                </tr>
                <tr>
                    <td>Number of Tables</td>
                    <td class="metric-value">{db_info['database_sizes']['tables_count']}</td>
                </tr>
            </table>
        </div>
    """
    html_content += '''
                        </div>
                    '''

    #   Upgrade Check Results section  
    html_content += ''' <div class="section">
        <div class="upgrade-check">
            <h2 >MySQL Upgrade Compatibility Check</h2>
    '''

    if upgrade_check_results:
        try:
            if isinstance(upgrade_check_results, str):
                results = json.loads(upgrade_check_results)
            else:
                results = upgrade_check_results

            # Get the output string
            output_str = results['output']
            
            # Find the first complete JSON object (the warning)
            warning_json_str = output_str[:output_str.find('}\n') + 1]
            
            # Get the main JSON object (everything after the warning)
            main_json_str = output_str[output_str.find('}\n') + 2:]
            #print("main_json_str:", main_json_str)
            try:
                # Parse the warning JSON
                #warning_data = json.loads(warning_json_str)
                # Parse the main JSON
                main_data = json.loads(main_json_str)
                # Combine the data
                #output_data = {**warning_data, **main_data}
                #print("main_data:",main_data)
                '''
                print("\nServer Information:")
                print(f"Server Address: {main_data.get('serverAddress', 'N/A')}")
                print(f"Current Version: {main_data.get('serverVersion', 'N/A')}")
                print(f"Target Version: {main_data.get('targetVersion', 'N/A')}")

                print("\nCheck Summary:")
                print(f"Error Count: {main_data.get('errorCount', 0)}")
                print(f"Warning Count: {main_data.get('warningCount', 0)}")
                print(f"Notice Count: {main_data.get('noticeCount', 0)}")
                '''
                
          

                # Add warning message if present
                if main_data.get('warning'):
                    html_content += f'''
                        <div class="warning-message">
                            ⚠️ {main_data['warning']}
                        </div>
                    '''

                # Server Information Section
                html_content += f'''
                    <h3 >Server Information</h3>
                    <table class="info-table">
                        <tr>
                            <th width="30%">Server Address</th>
                            <td>{main_data.get('serverAddress', 'N/A')}</td>
                        </tr>
                        <tr>
                            <th>Current Version</th>
                            <td>{main_data.get('serverVersion', 'N/A')}</td>
                        </tr>
                        <tr>
                            <th>Target Version</th>
                            <td>{main_data.get('targetVersion', 'N/A')}</td>
                        </tr>
                    </table>

                    <h3 >Check Summary</h3>
                    <table class="info-table">
                        <tr>
                            <th width="30%">Issues Found</th>
                            <td>
                                <span class="status-badge error-count">
                                    Errors: {main_data.get('errorCount', 0)}
                                </span>
                                <span class="status-badge warning-count">
                                    Warnings: {main_data.get('warningCount', 0)}
                                </span>
                                <span class="status-badge notice-count">
                                    Notices: {main_data.get('noticeCount', 0)}
                                </span>
                            </td>
                        </tr>
                        <tr>
                            <th>Summary</th>
                            <td>{main_data.get('summary', 'N/A')}</td>
                        </tr>
                    </table>
                '''

                #  Checks Performed section
                if main_data.get('checksPerformed'):
                    html_content += '''
                        <h3 >Detailed Check Results</h3>
                        <table class="info-table">
                                <tr>
                                    <th>Check ID</th>
                                    <th>Title</th>
                                    <th>Detected Problems</th>
                                </tr>
                    '''

                    for check in main_data['checksPerformed']:
                        #print("checksPerformed:- check",check)

                        check_id = check.get('id', 'N/A')
                        title = check.get('title', 'N/A')
                        title = title.replace('<', '&lt;').replace('>', '&gt;').replace("'", '&apos;').replace('"', '&quot;')
                        status = check.get('status', 'N/A')
                        status_class = 'status-ok' if status == 'OK' else 'status-error'
                        status_icon = '✓' if status == 'OK' else '⚠'

                        problems = check.get('detectedProblems', [])
                        if not problems:
                            problems_html = '<span class="no-problems">No issues detected</span>'
                        else:
                            problems_html = '<ul class="problems-list">'
                            for problem in problems:
                                if isinstance(problem, dict):
                                    level = problem.get('level', '')
                                    description = problem.get('description', '')
                                    problems_html += f'<li><strong>{level}:</strong> {description}</li>'
                            problems_html += '</ul>'
                        
                        if problems:
                            problems_html = '<ul class="problems-list">'
                            for problem in problems:
                                if isinstance(problem, dict):
                                    level = problem.get('level', '')
                                    description = problem.get('description', '')
                                    problems_html += f'<li>{level}: {description}</li>'
                                else:
                                    problems_html += f'<li>{problem}</li>'
                            problems_html += '</ul>'
                        else:
                            problems_html = '<span class="no-problems">No issues detected</span>'

        
                        '''
                        print('Check ID:',check.get('id', 'N/A'))
                        print('Title:',check.get('title', 'N/A'))
                        print('Status:',check.get('status', 'N/A'))
                        print('Detected Problems:',problems_html)
                        '''
                        html_content += f'''
                            <tr>
                                <td class="check-id">{check_id}</td>
                                <td>{title}</td>
                    
                                <td>{problems_html}</td>
                            </tr>
                            
                        '''
            #  Manual Checks 
                if main_data.get('manualChecks'):
                    html_content += '''
                        <table class="info-table">
                        <h3> Manual Checks </h3>
                                <tr>
                                    <th>Check ID</th>
                                    <th>Title</th>
                                    <th>Description</th>
                                    <th>DocumentationLink</th>
                                </tr>
                    '''

                    for mcheck in main_data['manualChecks']:
                        print("checksPerformed:- check",check)

                        mcheck_id = mcheck.get('id', 'N/A')
                        mtitle = mcheck.get('title', 'N/A')
                        mtitle = title.replace('<', '&lt;').replace('>', '&gt;').replace("'", '&apos;').replace('"', '&quot;')
                        mdescription = mcheck.get('description', 'N/A')
                        mdocumentationLink = mcheck.get('documentationLink', [])

                        html_content += f'''
                            <tr>
                                <td class="check-id">{mcheck_id}</td>
                                <td>{mtitle}</td>
                                <td>{mdescription} </td>
                                <td>{mdocumentationLink}</td>
                            </tr>
                        '''





                    html_content += '''
                        </table>
                        </div>
                        </div>
                    '''

            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {str(e)}")
                print("Warning JSON:", warning_json_str)
                print("Main JSON:", main_json_str)

        except Exception as e:
            print(f"Error processing upgrade check results: {str(e)}")
            traceback.print_exc()




    
    html_content += "</div>"  # Close the section



    html_content += """
    </body>
    </html>
    """
    if not os.path.exists("precheck_report"):
            os.makedirs("precheck_report", exist_ok=True)
    with open(f"precheck_report/{filename}", 'w', encoding='utf-8') as f:

        f.write(html_content)

    s3 = boto3.client('s3')
    s3.upload_file( f"precheck_report/{filename}", bucket, f"precheck_report/{filename}")
    

    return filename


def main(Config,section):
    """Main function to run the pre-check tool"""
    #print("=== RDS MySQL 5.7 to 8.0 Upgrade Pre-check Tool ===\n")
        
    connection = None
    try:

        cluster_type = Config.get(section, 'cluster_type').lower()

        if cluster_type == 'rds':
            # Get connection details and connect...
            cluster_instance_id = Config.get(section, 'rds_instance_identifier')
            region = Config.get(section, 'region')
            #print(f"Getting rds instance {cluster_instance_id} endpoint details")
            # user = pwinput.pwinput(prompt=f"Enter {cluster_instance_id} database  username: ", mask='*')
            # password = pwinput.pwinput(prompt=f"Enter {cluster_instance_id} database user password: ", mask='*')

            credentials_secret_name = Config.get(section, 'credentials_secret_name')
            user, password = get_credentials_from_secret(credentials_secret_name, region)
            rds_client = get_rds_connection(region)
            endpoint_result = get_rds_instance_endpoint(rds_client, cluster_instance_id)
            if endpoint_result is None:
                print(f"Failed to get endpoint for RDS instance {cluster_instance_id}")
                return
            host, port = endpoint_result
            connection = connect_to_rds(host, user, password, port)
        elif cluster_type == 'aurora':
            # Get connection details and connect...
            cluster_instance_id = Config.get(section, 'aurora_cluster')  
            aurora_instance_id = cluster_instance_id.split('-cluster')[0]

            region = Config.get(section, 'region')     
            #print(f"Getting Aurora cluster {cluster_instance_id} endpoint details")
            # user = pwinput.pwinput(prompt=f"Enter {cluster_instance_id} database  username: ", mask='*')
            # password = pwinput.pwinput(prompt=f"Enter {cluster_instance_id} database user password: ", mask='*')

            credentials_secret_name = Config.get(section, 'credentials_secret_name')
            user, password = get_credentials_from_secret(credentials_secret_name, region)
            rds_client = get_rds_connection(region)
            endpoint_result = get_db_cluster_endpoint(rds_client, cluster_instance_id)
            if endpoint_result is None:
                print(f"Failed to get endpoint for Aurora cluster {cluster_instance_id}")
                return
            host, port = endpoint_result
            connection = connect_to_rds(host, user, password, port)
        else:
            #print("Unsupported cluster type. Please use 'rds' or 'aurora'.")
            return
         # Get MySQL version information
        mysql_version = get_mysql_version(connection)
        #print(f"MySQL Version: {mysql_version['version']}")
        # Get RDS specific checks
        if cluster_type == 'aurora':
            rds_checks = check_rds_specific_requirements(connection,region,aurora_instance_id)
        else:
            rds_checks = check_rds_specific_requirements(connection,region,cluster_instance_id)

        # Get blue/green deployment limitations
        #print("blue/green deployment limitations before")
        if cluster_type == 'aurora':
            blue_green_limitations = check_rds_blue_green_limitations(connection,aurora_instance_id,region)
        else:
            blue_green_limitations = check_rds_blue_green_limitations(connection,cluster_instance_id,region)

        #print("blue/green deployment limitations after")
        #print("++++blue_green_limitations+++",blue_green_limitations)
        # Run MySQL Shell upgrade checker
        # Run upgrade check
        print("\nRunning MySQL upgrade compatibility check...")
        upgrade_check_results = check_server_upgrade(host, user, password, port)
        print("MySQL Shell Server Upgrade Checker Results status:" ,upgrade_check_results['status'])
    

        databases_info = []
        # Get all databases
        with connection.cursor() as cursor:
            cursor.execute("SHOW DATABASES; ")
            databases = [db['Database'] for db in cursor.fetchall() 
                        if db['Database'] not in ('information_schema', 'mysql', 'performance_schema', 'sys','innodb')]
            #print(f"\nFound {len(databases)} user databases: {', '.join(databases)}")

        # Process each database
        for database in databases:
            #print(f"\nProcessing database: {database}")
            try:
                # Gather all information for this database
                db_info = {
                    'database': database,
                    'mysql_version': mysql_version,
                    'database_sizes': get_database_sizes(connection, database)
                }
                #print("db_info details :" ,db_info)
                databases_info.append(db_info)
                
            except Exception as e:
                print(f"Error processing database {database}: {str(e)}")
                continue
        
        bucket = Config.get(section, 'bucket_name') 
        
        # Add RDS specific checks
        rds_compatibility = check_rds_version_compatibility(connection)

        # Generate single report with all database information
        filename = generate_html_report(
            databases_info, 
            mysql_version, 
            rds_checks, 
            rds_compatibility,
            blue_green_limitations,
            upgrade_check_results,
            cluster_instance_id,
            bucket
        )
        print(f"\nGenerated consolidated report: {filename}")
        
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        if connection:
            connection.close()

def download_s3_file(s3_path):
    """Download S3 file and return local path"""
    if s3_path.startswith('s3://'):
        s3_parts = s3_path[5:].split('/', 1)
        bucket = s3_parts[0]
        key = s3_parts[1]
        local_file = os.path.basename(key)
        s3 = boto3.client('s3')
        s3.download_file(bucket, key, local_file)
        return local_file
    return s3_path

if __name__ == "__main__":
    import sys
    try:
        print("Starting MySQL upgrade prechecker...")
        print(f"Arguments: {sys.argv}")
        
        config_file = sys.argv[1] if len(sys.argv) > 1 else "config.ini"
        print(f"Config file: {config_file}")
        
        config_file = download_s3_file(config_file)
        print(f"Local config file: {config_file}")
        
        if not os.path.exists(config_file):
            print(f"ERROR: Config file {config_file} not found")
            sys.exit(1)
            
        Config = configparser.ConfigParser()
        Config.read(config_file)
        sections = Config.sections()
        print(f"Config sections: {sections}")
        
        if not sections:
            print("ERROR: No sections found in config file")
            sys.exit(1)
            
        for section in sections:
            print(f"Processing section: {section}")
            try:
                target_parameter_family = Config.get(section, 'target_parameter_family').lower()
                print(f"Target parameter family: {target_parameter_family}")
                
                if target_parameter_family.__contains__('mysql'):
                    print(f"Running main function for section: {section}")
                    main(Config, section)
                else:
                    print(f"Skipping section {section} - not MySQL")
            except Exception as e:
                print(f"ERROR in section {section}: {str(e)}")
                traceback.print_exc()
                continue
                
        print("MySQL upgrade prechecker completed successfully")
        
    except Exception as e:
        print(f"FATAL ERROR: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

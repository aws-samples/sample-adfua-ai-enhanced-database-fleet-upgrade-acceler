import pymysql as mysql
import pg8000
import os
import logging

logger = logging.getLogger(__name__)
log_format='%(asctime)s [%(levelname)s] %(filename)s - %(message)s'
formatter = logging.Formatter(log_format)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.setLevel(logging.INFO)


def _mysql_ssl_args():
    """
    Build TLS args for pymysql. When the RDS global CA bundle is present
    (see Dockerfile), the server certificate is verified. Otherwise TLS is
    still required for the connection (encrypted, without CA pinning) so
    credentials never traverse the network in cleartext.
    """
    ca_path = os.environ.get("RDS_CA_BUNDLE", "/etc/ssl/certs/rds-global-bundle.pem")
    if os.path.exists(ca_path):
        return {"ca": ca_path}
    logger.warning("RDS CA bundle not found at %s; using TLS without CA verification", ca_path)
    return {}


class Mysql_connector:
    def __init__(self,host,port,user,password,database):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database

    def get_connection(self):
        try:
            connection = mysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                ssl=_mysql_ssl_args(),
            )
            return connection
        except mysql.connect.Error as err:
            print(f"Error: {err}")
            return None
    def exec_query(self,query):
        try:
            conn = self.get_connection()
            cur = conn.cursor() 
            cur.execute(query) #("select * from INFORMATION_SCHEMA.PROCESSLIST")
            output = cur.fetchall()
            conn.close()
            return output
        except Exception as e:
            logger.warning(f"Error in executing the mysql query: {e}")
        # print("Below queries are still running do you want to continue to switch over")
        # for i in output:
        #     print(i)
    # def kill_ids(self,id):
    #     try:
    #         conn = self.get_connection()
    #         cur = conn.cursor()
    #         cur.execute(f"kill {id}") 
    #         # conn.commit()
    #         conn.close()
    #         return True
    #     except Exception as e:
    #         logger.warning(f"Error in killing job {id}: {e}")

class postgres_connector:
    def __init__(self,host,port,user,password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def get_connection(self):
        try:
            connection = pg8000.dbapi.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password
            )
            return connection
        except pg8000.Error as err:
            print(f"Error: {err}")
            return None
    def exec_query(self,query):
        try:
            conn = self.get_connection()
            cur = conn.cursor() 
            cur.execute(query)
            output = cur.fetchall()
            conn.close()
            return output
        except Exception as e:
            logger.warning(f"Error in executing the postgres query: {e}")
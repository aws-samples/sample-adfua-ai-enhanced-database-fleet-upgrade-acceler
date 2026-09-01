import boto3,configparser
import time
import log_writer

class AuroraBlueGreenDeployment:
    def __init__(self, region_name,logger):
        self.rds = boto3.client('rds', region_name=region_name)
        self.logger = logger

    def create_cluster_parameter_group(self,cluster_name,parameter_group_family):
        parameter_group_name= f"{cluster_name}-{parameter_group_family.replace('.','')}-params"
        self.logger.info(f"creating parameter group {parameter_group_name}")
        try:
            response = self.rds.create_db_cluster_parameter_group(
                DBClusterParameterGroupName= parameter_group_name,
                DBParameterGroupFamily=parameter_group_family,
                Description=f'''Parameter group for {cluster_name} with family {parameter_group_family}''',
                )
            return response['DBClusterParameterGroup']['DBClusterParameterGroupName']

        except self.rds.exceptions.DBParameterGroupAlreadyExistsFault as e:
            self.logger.info(f"Parameter group already exists. Skipping creation.")
            return parameter_group_name
        except Exception as e:
            self.logger.info(f"Unable to create Parameter group: {e}")
            return None

    def create_db_parameter_group(self,cluster_name,parameter_group_family):
        parameter_group_name= f"{cluster_name}-{parameter_group_family.replace('.','')}-db-params"
        self.logger.info(f"creating parameter group {parameter_group_name}")
        try:
            response = self.rds.create_db_parameter_group(
                DBParameterGroupName=parameter_group_name,
                DBParameterGroupFamily=parameter_group_family,
                Description=f'''Parameter group for {cluster_name} with family {parameter_group_family}'''
                )
            return response['DBParameterGroup']['DBParameterGroupName']
        except self.rds.exceptions.DBParameterGroupAlreadyExistsFault:
            self.logger.info("Parameter group already exists. Skipping creation.")
            return parameter_group_name
        except Exception as e:
            self.logger.info(f"Unable to create Parameter group: {e}")
            return None

    def modify_mysql_cluster_parameter_group(self,parameter_group_name):
        self.logger.info(f"modifying parameter group {parameter_group_name}")
        try:
            response = self.rds.modify_db_cluster_parameter_group(
                DBClusterParameterGroupName=parameter_group_name, #     'mysql57-params',
                    Parameters=[
                        {
                            'ParameterName': 'binlog_format',
                            'ParameterValue': 'ROW',
                            'ApplyMethod': 'pending-reboot'
                        },
                        {
                            'ParameterName': 'binlog_checksum',
                            'ParameterValue': 'NONE',
                            'ApplyMethod': 'pending-reboot'
                        }
                    ]
                )
            return response['DBClusterParameterGroupName']
        except Exception as e:
            self.logger.info(f"Unable to modify Parameter group: {e}")
            return None
    
    def modify_postgres_db_parameter_group(self,parameter_group_name):
        self.logger.info(f"updating parameter group {parameter_group_name}")
        try:
            response = self.rds.modify_db_parameter_group(
                DBParameterGroupName=parameter_group_name, 
                    Parameters=[
                        {
                            'ParameterName': 'rds.logical_replication',
                            'ParameterValue': "1",
                            'ApplyMethod': 'pending-reboot'
                        }
                    ]
                )
            return response['DBParameterGroupName']
        except Exception as e:
            self.logger.info(f"Unable to modify Parameter group: {e}")
            return None
    def modify_postgres_cluster_parameter_group(self,parameter_group_name):
        self.logger.info(f"modifying parameter group {parameter_group_name}")
        try:
            response = self.rds.modify_db_cluster_parameter_group(
                DBClusterParameterGroupName=parameter_group_name, #     'mysql57-params',
                    Parameters=[
                        {
                            'ParameterName': 'rds.logical_replication',
                            'ParameterValue': "1",
                            'ApplyMethod': 'pending-reboot'
                        }
                    ]
                )
            return response['DBClusterParameterGroupName']
        except Exception as e:
            self.logger.info(f"Unable to modify Parameter group: {e}")
            return None

    def modify_db_cluster(self,cluster_identifier,parameter_group_name):
        self.logger.info(f"modifying db cluster {cluster_identifier} with parameter group {parameter_group_name}")
        try:
            response = self.rds.modify_db_cluster(DBClusterIdentifier=cluster_identifier,
                                            ApplyImmediately=True,
                                            DBClusterParameterGroupName=parameter_group_name) #'mysql57-params')
            return response
        except Exception as e:
            self.logger.info(f"Error in modifying dn cluster parameter group: {e}")
            return None
    #get source db instance arn
    def get_source_aurora_arn(self,cluster_identifier):
        try:
            response = self.rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
            return response['DBClusters'][0]['DBClusterArn']
            # instance = response['DBInstances'][0]['DBInstanceArn']
            # return instance
        except Exception as e:
            self.logger.info(f"Error getting cluster {cluster_identifier} arn details: {e}")
            return None

    def get_db_cluster_endpoint(self,cluster_identifier):
        try:
            response = self.rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
            end_point = response['DBClusters'][0]['Endpoint']
            port = response['DBClusters'][0]['Port']
            self.logger.info(f"DB cluster endpoint details: {end_point} {port}")
            return end_point,port
        except Exception as e:
            self.logger.debug(f"Error getting cluster {cluster_identifier} endpoint details: {e}")
            return None
    
    def modify_writer_instance(self,instance_identifier,parameter_group_name):
        try:
            response = self.rds.modify_db_instance(DBInstanceIdentifier=instance_identifier,
                                            ApplyImmediately=True,
                                            DBParameterGroupName=parameter_group_name) #'mysql57-params')
            return response
        except Exception as e:
            self.logger.info(f"Error in modifying dn cluster parameter group: {e}")
            return None

    def reboot_aurora_writer_instance(self,writer_instance):
        self.logger.info(f"Rebooting writer instance {writer_instance}")
        try:
            response = self.rds.reboot_db_instance(
                DBInstanceIdentifier=writer_instance
            )
            return response
        except Exception as e:
            self.logger.info(f"Error rebooting aurora cluster {writer_instance} : {e}")
            return None

    def get_writer_instance_status(self,instance_identifier):
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
            instance_status = response['DBInstances'][0]['DBInstanceStatus']
            return instance_status
        except Exception as e:
            self.logger.info(f"Error getting Aurora writer instance details: {e}")
            return None

    def get_aurora_cluster_status(self,cluster_identifier):
        try:
            response = self.rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
            cluster_status = response['DBClusters'][0]['Status']
            return cluster_status
        except Exception as e:
            self.logger.info(f"Error getting Aurora cluster details: {e}")
            return None

    def get_aurora_writer_instance(self,cluster_identifier):
        self.logger.info(f"Getting writer instance details for cluster {cluster_identifier}")
        try:
            response = self.rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
            instance_ids = response['DBClusters'][0]['DBClusterMembers']
            for i in instance_ids:
                if i['IsClusterWriter']:
                    return i['DBInstanceIdentifier']
        except Exception as e:
            self.logger.info(f"Error getting Aurora cluster writer instance details: {e}")
            return None
            
    def describe_db_cluster_parameter_groups(self, cluster_identifier):
        self.logger.info(f"Getting cluster parameter group details for cluster {cluster_identifier}")
        try:
            response = self.rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
            parameter_group = response['DBClusters'][0]['DBClusterParameterGroup']
            return parameter_group
        except Exception as e:
            self.logger.info(f"Error getting Aurora cluster parameter group details: {e}")
            return None

    def create_blue_green_deployment(self,
                                   deployment_name,
                                   source_cluster_arn,
                                   target_engine_version,
                                   target_db_param_group=None,
                                   target_cluster_param_group=None):
        try:
            params = {
                'BlueGreenDeploymentName': deployment_name,
                'Source': source_cluster_arn,
                'TargetEngineVersion': target_engine_version,
                'TargetDBParameterGroupName': target_db_param_group,
                'TargetDBClusterParameterGroupName':target_cluster_param_group

            }

            # Add parameter group if specified
            # if target_db_param_group:
            #     params['TargetDBClusterParameterGroupName'] = target_db_param_group

            response = self.rds.create_blue_green_deployment(**params)

            return response['BlueGreenDeployment']['BlueGreenDeploymentIdentifier']
        except self.rds.exceptions.BlueGreenDeploymentAlreadyExistsFault:
            self.logger.info("Blue green deployment already created. Skipping creation.")
            return True
        except self.rds.exceptions.ClientError as e:
            self.logger.info(f"Error creating blue-green deployment: {e}")
            raise

    def get_blue_green_deployment_id(self,instance_identifier):
        self.logger.info(f"Getting deployment id for {instance_identifier}")
        try:
            response = self.rds.describe_blue_green_deployments()
            for bgids in response['BlueGreenDeployments']:
                if bgids['BlueGreenDeploymentName'].split('-')[0] == instance_identifier.split('-')[0]:
                    self.logger.info(f"deployment details of {instance_identifier}: {bgids}")
                    return bgids['BlueGreenDeploymentIdentifier']
        except Exception as e:
            self.logger.info(f"Error getting blue green deployment id: {e}")
            return None

    def get_deployment_status(self, deployment_identifier):
        try:
            response = self.rds.describe_blue_green_deployments(
                BlueGreenDeploymentIdentifier=deployment_identifier
            )
            return response['BlueGreenDeployments'][0]['Status']
        except self.rds.exceptions.ClientError as e:
            self.logger.info(f"Error getting deployment status: {e}")
            raise
    def get_target_cluster(self,deployment_id):
        try:
            response = self.rds.describe_blue_green_deployments(
                BlueGreenDeploymentIdentifier=deployment_id
            )
            return response['BlueGreenDeployments'][0]['Target'].split(":")[-1]
        except Exception as e:
            self.logger.info(f"Error getting target db instace identifier: {e}")
            return None
    def get_parameter_group(self,instance_identifier):
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
            parameter_group = response['DBInstances'][0]['DBParameterGroups'][0]['DBParameterGroupName']
            return parameter_group
        except Exception as e:
            self.logger.info(f"Error getting RDS instance option group details: {e}")
            return None
    def get_parameter_value(self, parameter_group_name, parameter_name):
        try:
            paginator = self.rds.get_paginator('describe_db_parameters')
            for page in paginator.paginate(DBParameterGroupName=parameter_group_name):
                for parameter in page['Parameters']:
                    if parameter.get('ParameterName') == parameter_name:
                        print(parameter.get('ParameterName'))
                        print(parameter.get('ParameterValue'))
                        return parameter.get('ParameterValue')
            return None
        except Exception as e:
            self.logger.info(f"Error getting parameter value for {parameter_name}: {e}")
            return None    

    def wait_for_deployment_available(self,deployment_identifier):
        self.logger.info("Waiting for deployment to be available...")
        time.sleep(60)

        while True:
            status = self.get_deployment_status(deployment_identifier)
            if status == 'AVAILABLE' :
                self.logger.info("Deployment is now available")
                return True
            elif status in ['FAILED', 'DELETED','DELETING','INVALID_CONFIGURATION']:
                self.logger.info(f"Deployment failed or was deleted. Status: {status}")
                return False
            elif status == 'PROVISIONING':
                target_cluster =self.get_target_cluster(deployment_identifier)
                target_cluster_status = self.get_aurora_cluster_status(target_cluster)
                self.logger.info(f"Blue green deployment {deployment_identifier} is in provisioning state and green cluster {target_cluster} is in {target_cluster_status} state")
                time.sleep(60)

            else:
                self.logger.info(f"Current status: {status}. Waiting...")
                time.sleep(60)

            # return False

    def switchover_deployment(self,deployment_identifier):
        try:
            response = self.rds.switchover_blue_green_deployment(
                BlueGreenDeploymentIdentifier=deployment_identifier,
                SwitchoverTimeout=300  # 5 minutes timeout
            )
            return response
        except Exception as e:
            self.logger.info(f"Error during switchover: {e}")
            return None

    def delete_deployment(self,deployment_identifier):
        self.logger.info(f"Deleting Blue Green Deployment {deployment_identifier}...")
        try:
            response = self.rds.delete_blue_green_deployment(
                BlueGreenDeploymentIdentifier=deployment_identifier
            )
            return response
        except Exception as e:
            self.logger.info(f"Error deleting deployment: {e}")
            return None
    
    def create_db_cluster_snapshot(self,instance_identifier):
        self.logger.info(f"Creating snapshot to {instance_identifier}...")
        try:
            response = self.rds.create_db_cluster_snapshot(
                    DBClusterSnapshotIdentifier=f"{instance_identifier}-snapshot",
                    DBClusterIdentifier=instance_identifier
                )
            return response ['DBClusterSnapshot']['DBClusterSnapshotIdentifier']
        except self.rds.exceptions.DBClusterSnapshotAlreadyExistsFault:
            self.logger.info(f"Snapshot already created to {instance_identifier}")
            response = self.describe_db_cluster_snapshots(instance_identifier)
            return response['DBClusterSnapshots'][0]['DBClusterSnapshotIdentifier']

        except self.rds.exceptions.ClientError as e:
            self.logger.info(f"Error creating snapshot to {instance_identifier}: {e}")
            raise   

    def describe_db_cluster_snapshots(self,instance_identifier):
        self.logger.info(f"checking status of snapshot {instance_identifier}...")
        try:
            response = self.rds.describe_db_cluster_snapshots(
                    DBClusterIdentifier=f"{instance_identifier}"
                )
            return response
        except self.rds.exceptions.ClientError as e:
            self.logger.info(f"Error getting status of snapshot of {instance_identifier}: {e}")
            raise                       
    
    def wait_for_snapshot_available(self,instance_identifier):
        self.logger.info("Waiting for Snapshot to be available...")
        # time.sleep(60)

        while True:
            response = self.describe_db_cluster_snapshots(instance_identifier)
            status = response['DBClusterSnapshots'][0]['Status']
            if status.upper() == 'AVAILABLE' :
                self.logger.info("Snapshot is now available")
                return True
            elif status.upper() in ['FAILED', 'DELETED','DELETING']:
                self.logger.info(f"Snapshot creation was deleted. Status: {status}")
                return False
            elif status.upper() in ['CREATING','COPYING']:
                self.logger.info(f"Snapshot creation for instance {instance_identifier} is in {status} state")
                time.sleep(60)

class RDSBlueGreenDeployment:
    def __init__(self, region,logger):
        # Initialize session and RDS client
        self.rds = boto3.client('rds', region_name=region)
        self.logger = logger
        # self.config=Config

    #Get all db db instance details
    def get_rds_instances(self):
        try:
            response = self.rds.describe_db_instances()
            # instance = response['DBInstances']
            instances_identifier = [value['DBInstanceIdentifier'] for value in response['DBInstances']]
            return instances_identifier
        except Exception as e:
            self.logger.info(f"Error getting RDS instances details: {e}")

    # Get source instance details
    def get_rds_instance_status(self,instance_identifier):
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
            instance_status = response['DBInstances'][0]['DBInstanceStatus']
            return instance_status
        except Exception as e:
            self.logger.info(f"Error getting RDS instance status: {e}")
            return None

    def get_option_group_status(self,instance_identifier):
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
            option_group = response['DBInstances'][0]['OptionGroupMemberships'][0]['OptionGroupName']
            if option_group.__contains__('default:'):
                self.logger.info("DB instance attached with default option group so proceeding with Blue Green deployment")
            else:
                self.logger.info(f"please change the option group from {option_group} to default option group before proceeding with BG deployment")
                exit()
        except Exception as e:
            self.logger.info(f"Error getting RDS instance option group details: {e}")
            return None
    
    def get_parameter_group(self,instance_identifier):
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
            parameter_group = response['DBInstances'][0]['DBParameterGroups'][0]['DBParameterGroupName']
            return parameter_group
        except Exception as e:
            self.logger.info(f"Error getting RDS instance option group details: {e}")
            return None
    
    def get_parameter_value(self, parameter_group_name, parameter_name):
        try:
            paginator = self.rds.get_paginator('describe_db_parameters')
            for page in paginator.paginate(DBParameterGroupName=parameter_group_name):
                for parameter in page['Parameters']:
                    if parameter.get('ParameterName') == parameter_name:
                        print(parameter.get('ParameterName'))
                        print(parameter.get('ParameterValue'))
                        return parameter.get('ParameterValue')
            return None
        except Exception as e:
            self.logger.info(f"Error getting parameter value for {parameter_name}: {e}")
            return None

    def create_db_parameter_group(self,instance_identifier,parameter_group_family):
        parameter_group_name= f"{instance_identifier}-{parameter_group_family.replace('.','')}-params"
        self.logger.info(f"creating parameter group {parameter_group_name}")
        try:
            response = self.rds.create_db_parameter_group(
                DBParameterGroupName=parameter_group_name,
                DBParameterGroupFamily=parameter_group_family,
                Description=f'''Parameter group for {instance_identifier} with family {parameter_group_family}'''
                )
            return response['DBParameterGroup']['DBParameterGroupName']
        except self.rds.exceptions.DBParameterGroupAlreadyExistsFault:
            self.logger.info("Parameter group already exists. Skipping creation.")
            return parameter_group_name
        except Exception as e:
            self.logger.info(f"Unable to create Parameter group: {e}")
            return None

    def modify_mysql_db_parameter_group(self,parameter_group_name):
        try:
            response = self.rds.modify_db_parameter_group(
                DBParameterGroupName=parameter_group_name, #     'mysql57-params',
                    Parameters=[
                        {
                            'ParameterName': 'binlog_format',
                            'ParameterValue': 'ROW',
                            'ApplyMethod': 'pending-reboot'
                        },
                        {
                            'ParameterName': 'binlog_checksum',
                            'ParameterValue': 'NONE',
                            'ApplyMethod': 'pending-reboot'
                        }
                    ]
                )
            return response['DBParameterGroupName']
        except Exception as e:
            self.logger.info(f"Unable to modify Parameter group: {e}")
            return None

    def modify_postgres_db_parameter_group(self,parameter_group_name):
        self.logger.info(f"updating parameter group {parameter_group_name}")
        try:
            response = self.rds.modify_db_parameter_group(
                DBParameterGroupName=parameter_group_name, 
                    Parameters=[
                        {
                            'ParameterName': 'rds.logical_replication',
                            'ParameterValue': "1",
                            'ApplyMethod': 'pending-reboot'
                        }
                    ]
                )
            return response['DBParameterGroupName']
        except Exception as e:
            self.logger.info(f"Unable to modify Parameter group: {e}")
            return None

    def modify_db_instance(self,instance_identifier,parameter_group_name):
        try:
            response = self.rds.modify_db_instance(DBInstanceIdentifier=instance_identifier,
                                            ApplyImmediately=True,
                                            DBParameterGroupName=parameter_group_name) #'mysql57-params')
            return response
        except Exception as e:
            self.logger.info(f"Error in modifying dn cluster parameter group: {e}")
            return None

    def get_rds_instance_endpoint(self,instance_identifier):
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
            end_point = response['DBInstances'][0]['Endpoint']['Address']
            port = response['DBInstances'][0]['Endpoint']['Port']
            self.logger.info(f"RDS instance details: {end_point} {port}")
            return end_point,port
        except Exception as e:
            self.logger.debug(f"Error getting RDS instance details: {e}")
            return None

    def get_target_db_instance(self,deployment_id):
        try:
            response = self.rds.describe_blue_green_deployments(
                BlueGreenDeploymentIdentifier=deployment_id
            )
            return response['BlueGreenDeployments'][0]['Target'].split(":")[-1]
        except Exception as e:
            self.logger.info(f"Error getting target db instace identifier: {e}")
            return None

    #get source db instance arn
    def get_source_rds_arn(self,instance_identifier):
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
            instance = response['DBInstances'][0]['DBInstanceArn']
            return instance
        except Exception as e:
            self.logger.info(f"Error getting RDS instance arn: {e}")
            return None


    #create blue_green_deployement

    def create_blue_green_deployment(self,
                                   deployment_name,
                                   source_cluster_arn,
                                   target_engine_version,
                                   target_param_group):
        try:
            params = {
                'BlueGreenDeploymentName': deployment_name,
                'Source': source_cluster_arn,
                'TargetEngineVersion': target_engine_version,
                'TargetDBParameterGroupName': target_param_group

            }

            # Add parameter group if specified
            # if target_param_group:
            #     params['TargetDBClusterParameterGroupName'] = target_param_group

            response = self.rds.create_blue_green_deployment(**params)

            return response['BlueGreenDeployment']['BlueGreenDeploymentIdentifier']
        except self.rds.exceptions.BlueGreenDeploymentAlreadyExistsFault:
            self.logger.info("Blue green deployment already created. Skipping creation.")
            return True
        except self.rds.exceptions.ClientError as e:
            self.logger.info(f"Error creating blue-green deployment: {e}")
            raise

    def get_blue_green_deployment_id(self,instance_identifier):
        self.logger.info(f"Getting deployment for {instance_identifier}")
        try:
            response = self.rds.describe_blue_green_deployments()
            for bgids in response['BlueGreenDeployments']:
                if bgids['BlueGreenDeploymentName'].split('-')[0] == instance_identifier.split('-')[0]:
                    self.logger.info(f"deployment details of {instance_identifier}: {bgids}")
                    return bgids['BlueGreenDeploymentIdentifier']
        except Exception as e:
            self.logger.info(f"Error getting blue green deployment id: {e}")
            return None

    def get_deployment_status(self,deployment_id):
        try:
            response = self.rds.describe_blue_green_deployments(
                BlueGreenDeploymentIdentifier=deployment_id
            )
            return response['BlueGreenDeployments'][0]['Status']
        except Exception as e:
            self.logger.info(f"Error getting deployment status: {e}")
            return None

    def wait_for_deployment_available(self,deployment_identifier, timeout_seconds=7200):
        self.logger.info(f"Waiting for deployment {deployment_identifier} to be available...")
        time.sleep(60)
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            status = self.get_deployment_status(deployment_identifier)
            if status == 'AVAILABLE' :
                self.logger.info("Deployment is now available")
                return True
            elif status in ['FAILED', 'DELETED','DELETING','INVALID_CONFIGURATION']:
                self.logger.info(f"Deployment failed or was deleted. Status: {status}")
                return False
            elif status == 'PROVISIONING':
                target_db_instance =self.get_target_db_instance(deployment_identifier)
                target_cluster_status = self.get_rds_instance_status(target_db_instance)
                self.logger.info(f"Blue green deployment {deployment_identifier} is in provisioning state and green instance {target_db_instance} is in {target_cluster_status} state")
                time.sleep(60)
                pass

            else:
                self.logger.info(f"Current status: {status}. Waiting...")
                time.sleep(60)

            # return False

    def switchover_deployment(self,deployment_identifier):
        try:
            response = self.rds.switchover_blue_green_deployment(
                BlueGreenDeploymentIdentifier=deployment_identifier,
                SwitchoverTimeout=300  # 5 minutes timeout
            )
            return response
        except Exception as e:
            self.logger.info(f"Error during switchover: {e}")
            return None

    def delete_deployment(self,deployment_identifier):
        self.logger.info(f"Deleting Blue Green Deployment {deployment_identifier}...")
        try:
            response = self.rds.delete_blue_green_deployment(
                BlueGreenDeploymentIdentifier=deployment_identifier
            )
            return response
        except Exception as e:
            self.logger.info(f"Error deleting deployment: {e}")
            return None

    def reboot_db_instance(self,instance_identifier):
        try:
            response = self.rds.reboot_db_instance(
                DBInstanceIdentifier=instance_identifier
            )
            return response
        except Exception as e:
            self.logger.info(f"Error rebooting RDS instance: {e}")
            return None
    def get_readreplica(self,instance_identifier):
        self.logger.info(f"getting read replica details of rds instance {instance_identifier}...")
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=instance_identifier)
            replicas = response['DBInstances'][0]['ReadReplicaDBInstanceIdentifiers']
            return replicas
        except Exception as e:
            self.logger.info(f"Error getting RDS instance read replica: {e}")
            return None
    def create_db_snapshot(self,instance_identifier):
        self.logger.info(f"Creating snapshot to {instance_identifier}...")
        try:
            response = self.rds.create_db_snapshot(
                    DBSnapshotIdentifier=f"{instance_identifier}-snapshot",
                    DBInstanceIdentifier=instance_identifier
                )
            return response['DBSnapshot']['DBSnapshotIdentifier']
        except self.rds.exceptions.DBSnapshotAlreadyExistsFault:
            self.logger.info(f"Snapshot already created to {instance_identifier}")
            response = self.describe_db_snapshots(instance_identifier)
            return response['DBSnapshots'][0]['DBSnapshotIdentifier']

        except self.rds.exceptions.ClientError as e:
            self.logger.info(f"Error creating snapshot to {instance_identifier}: {e}")
            raise

    def describe_db_snapshots(self,instance_identifier):
        self.logger.info(f"checking status of snapshot {instance_identifier}...")
        try:
            response = self.rds.describe_db_snapshots(
                    DBInstanceIdentifier=f"{instance_identifier}"
                )
            return response
        except self.rds.exceptions.ClientError as e:
            self.logger.info(f"Error getting status of snapshot of {instance_identifier}: {e}")
            raise   

    def wait_for_snapshot_available(self,instance_identifier):
        self.logger.info("Waiting for Snapshot to be available...")

        while True:
            response = self.describe_db_snapshots(instance_identifier)
            status = response['DBSnapshots'][0]['Status']
            if status.upper() == 'AVAILABLE' :
                self.logger.info("Snapshot is now available")
                return True
            elif status.upper() in ['FAILED', 'DELETED','DELETING']:
                self.logger.info(f"Snapshot creation was deleted. Status: {status}")
                return False
            elif status.upper() in ['CREATING','COPYING']:
                self.logger.info(f"Snapshot creation for instance {instance_identifier} is in {status} state")
                time.sleep(60)


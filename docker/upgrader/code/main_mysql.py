import time
import configparser
import log_writer
import cloudwatch_log
import bgd_automation
import boto3
import os
import sys

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


def rds_main(Config,section):
    blue_instance = Config.get(section,'rds_instance_identifier')
    logger = log_writer.CustomLogger(instance_name=blue_instance).get_logger()

    # Initialize the deployment manager
    bgd = bgd_automation.RDSBlueGreenDeployment(region=Config.get(section,'region'),logger=logger)

    logger.info(f"Continuing with the Blue Green deployment of RDS instance {blue_instance} ...")
    cw_logs=cloudwatch_log.replica_log(region=Config.get(section,'region'))
    replicat_instance = bgd.get_readreplica(blue_instance)
    if len(replicat_instance)>0:
        for instance_identifier in replicat_instance:
            lag = cw_logs.get_rds_replica_lag(instance_identifier)
            while lag != 0 :
                lag = cw_logs.get_rds_replica_lag(instance_identifier)
                if lag is not None:
                    if lag != 0:
                        logger.info(f"WARNING:Replication lag detected: {lag} seconds")
                    else:
                        logger.info(f"Current replication lag: {lag} seconds")
                time.sleep(60)

    else:
        logger.info(f"{blue_instance} instance doesn't have any read replicas")

    # logger.info(f"Taking the backup snapshot of {blue_instance} ...")
    # snapshot_identifier = bgd.create_db_snapshot(blue_instance)
    # logger.info(f"Created the snapshot of {blue_instance} as {snapshot_identifier} ...")

    # if bgd.wait_for_snapshot_available(blue_instance):
    #     logger.info(f"Snapshot {snapshot_identifier} is available for {blue_instance}")
    # else:
    #     logger.info(f"Failed to create Snapshot for {blue_instance}")
    #     return
    
    new_parameter_group_name=bgd.create_db_parameter_group(instance_identifier=blue_instance,\
                                parameter_group_family=Config.get(section,'target_parameter_family'))

    logger.info(f"Creating Blue Green deployement for db instance: {blue_instance}")
    # Create the blue-green deployment
    # deployment_id = bgd.create_blue_green_deployment(blue_instance)
    deployment_id = bgd.create_blue_green_deployment(
        deployment_name=f"""{blue_instance}-bgd-deployment""",
        source_cluster_arn=bgd.get_source_rds_arn(blue_instance),
        target_engine_version=Config.get(section,'target_engine_version'),  # Specify your target version
        target_param_group=new_parameter_group_name
    )


    if not deployment_id:
        logger.info(f"Failed to create Blue Green deployement for {blue_instance}")
        return
    elif deployment_id == True:
        logger.info(f"Blue Green deployement already created for {blue_instance}")
        deployment_id = bgd.get_blue_green_deployment_id(blue_instance)
        target_db_instance = bgd.get_target_db_instance(deployment_id)
        logger.info(f"deployment id is: {deployment_id} for db instance: {blue_instance} and its green db {target_db_instance}")
        return deployment_id
    else:
        deployment_id = bgd.get_blue_green_deployment_id(blue_instance)
        logger.info(f"created Blue Green deployement and deployment id is: {deployment_id} for db instance: {blue_instance}")
        return deployment_id

def aurora_main(Config,section):
    # Initialize the deployment manager
    aurora_cluster = Config.get(section,'aurora_cluster')
    aws_region = Config.get(section, 'region')
    logger = log_writer.CustomLogger(instance_name=aurora_cluster).get_logger()

    bgd = bgd_automation.AuroraBlueGreenDeployment(region_name=aws_region,logger=logger)

    logger.info(f"Continuing with the Blue Green deployment of cluster {aurora_cluster}...")
    
    # logger.info(f"Taking the backup snapshot of {aurora_cluster} ...")
    # snapshot_identifier = bgd.create_db_cluster_snapshot(aurora_cluster)
    # logger.info(f"Created the snapshot of {aurora_cluster} as {snapshot_identifier} ...")

    # if bgd.wait_for_snapshot_available(aurora_cluster):
    #     logger.info(f"Snapshot {snapshot_identifier} is available for {aurora_cluster}")
    # else:
    #     logger.info(f"Failed to create Snapshot for {aurora_cluster}")
    #     return

    new_cluster_parameter_group_name = bgd.create_cluster_parameter_group(cluster_name=aurora_cluster,\
                                parameter_group_family=Config.get(section,'target_parameter_family'))
    logger.info(f"new cluster parameter group created {new_cluster_parameter_group_name} ")

    new_db_parameter_group_name=bgd.create_db_parameter_group(cluster_name=aurora_cluster,\
                                parameter_group_family=Config.get(section,'target_parameter_family'))
    logger.info(f"new db parameter group created {new_db_parameter_group_name} ")
    # modify_db_cluster = bgd.modify_db_cluster(aurora_cluster,modify_cluster_parameter_group)

    logger.info(f"Creating Blue Green deployement for Aurora Cluster: {aurora_cluster}")

    # Create deployment
    deployment_id = bgd.create_blue_green_deployment(
        deployment_name=f"""{aurora_cluster}-bgd-deployment""",
        source_cluster_arn=bgd.get_source_aurora_arn(cluster_identifier=aurora_cluster),
        target_engine_version=Config.get(section,'target_engine_version'),  # Specify your target version
        target_db_param_group=new_db_parameter_group_name,
        target_cluster_param_group=new_cluster_parameter_group_name
    )
    # start_time = time.time()

    if not deployment_id:
        logger.info(f"Failed to create Blue Green deployement for {aurora_cluster}")
        return 
    elif deployment_id == True:
        logger.info(f"Blue Green deployement already created for {aurora_cluster}")
        deployment_id = bgd.get_blue_green_deployment_id(aurora_cluster)
        target_cluster = bgd.get_target_cluster(deployment_id)
        logger.info(f"deployment id is: {deployment_id} for blue Aurora cluster:{target_cluster} and its green cluster {target_cluster}")
        return deployment_id
    else:
        deployment_id = bgd.get_blue_green_deployment_id(aurora_cluster)
        logger.info(f"created Blue Green deployement and deployment id is: {deployment_id} for aurora cluster: {aurora_cluster}")
        return deployment_id

def wait_for_availability(config, section, deployment_id, logger):
    """Wait until BG deployment is AVAILABLE and green instance/cluster is available."""
    cluster_type = config.get(section, 'cluster_type').lower()
    region       = config.get(section, 'region')

    if cluster_type == 'rds':
        bgd = bgd_automation.RDSBlueGreenDeployment(region=region, logger=logger)
        if not bgd.wait_for_deployment_available(deployment_identifier=deployment_id):
            logger.info("Deployment never became AVAILABLE.")
            return False
        target_db_instance = bgd.get_target_db_instance(deployment_id)
        target_db_status = None
        while target_db_status != 'available':
            time.sleep(60)
            target_db_status = bgd.get_rds_instance_status(target_db_instance)
            logger.info(f"Waiting for green instance {target_db_instance} — status: {target_db_status}")
        logger.info(f"Green instance {target_db_instance} is available. Deployment ready for switchover.")
        return True

    elif cluster_type == 'aurora':
        bgd = bgd_automation.AuroraBlueGreenDeployment(region_name=region, logger=logger)
        if not bgd.wait_for_deployment_available(deployment_identifier=deployment_id):
            logger.info("Deployment never became AVAILABLE.")
            return False
        target_cluster = bgd.get_target_cluster(deployment_id)
        target_cluster_status = None
        while target_cluster_status != 'available':
            time.sleep(60)
            target_cluster_status = bgd.get_aurora_cluster_status(target_cluster)
            logger.info(f"Waiting for green cluster {target_cluster} — status: {target_cluster_status}")
        logger.info(f"Green cluster {target_cluster} is available. Deployment ready for switchover.")
        return True

    return False


def process_task(config, section):
    cluster_type = config.get(section, 'cluster_type').lower()
    target_parameter_family = config.get(section, 'target_parameter_family').lower()
    if cluster_type == 'rds' and target_parameter_family.__contains__('mysql'):
        return rds_main(config, section)
    elif cluster_type == 'aurora' and target_parameter_family.__contains__('mysql'):
        return aurora_main(config, section)

def bg_main(Config, section, logger):
    start_time = time.time()
    deployment_id = process_task(Config, section)
    if not deployment_id:
        logger.info(f"Failed to create Blue Green deployment for {section}")
        return
    logger.info(f"Blue Green deployment created: {deployment_id}. Waiting for availability...")
    if wait_for_availability(Config, section, deployment_id, logger):
        elapsed = round((time.time() - start_time) / 60, 2)
        logger.info(f"Deployment {deployment_id} is AVAILABLE in {elapsed} mins. Ready for switchover.")
    else:
        logger.info(f"Deployment {deployment_id} did not reach AVAILABLE state.")

def main():
    try:
        print("Starting MySQL Blue/Green deployment tool...")
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
            
        logger = log_writer.CustomLogger(instance_name="main_method").get_logger()
        
        for section in sections:
            print(f"Processing section: {section}")
            try:
                target_parameter_family = Config.get(section, 'target_parameter_family').lower()
                print(f"Target parameter family: {target_parameter_family}")
                
                if target_parameter_family.__contains__('mysql'):
                    print(f"Running Blue/Green deployment for section: {section}")
                    bg_main(Config, section, logger)
                else:
                    print(f"Skipping section {section} - not MySQL")
            except Exception as e:
                print(f"ERROR in section {section}: {str(e)}")
                continue
                
        print("MySQL Blue/Green deployment completed successfully")
        
    except Exception as e:
        print(f"FATAL ERROR: {str(e)}")
        sys.exit(1)
    
if __name__ == "__main__":
    main()

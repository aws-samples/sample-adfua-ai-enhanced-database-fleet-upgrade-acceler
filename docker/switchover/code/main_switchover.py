import time
import configparser
import log_writer
import dbconnector
import bgd_automation
import boto3
import json
import os
import sys


def get_credentials_from_secret(secret_name, region):
    try:
        client = boto3.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        return secret.get('username'), secret.get('password')
    except Exception as e:
        print(f"Error getting credentials from secret {secret_name}: {e}")
        raise


def download_s3_file(s3_path):
    if s3_path.startswith('s3://'):
        s3_parts = s3_path[5:].split('/', 1)
        bucket, key = s3_parts[0], s3_parts[1]
        local_file = os.path.basename(key)
        boto3.client('s3').download_file(bucket, key, local_file)
        return local_file
    return s3_path


def rds_switchover(config, section):
    blue_instance = config.get(section, 'rds_instance_identifier')
    region        = config.get(section, 'region')
    logger        = log_writer.CustomLogger(instance_name=blue_instance).get_logger()
    bgd           = bgd_automation.RDSBlueGreenDeployment(region=region, logger=logger)

    # ── Find AVAILABLE deployment ─────────────────────────────────────────────
    deployment_id = bgd.get_blue_green_deployment_id(blue_instance)
    if not deployment_id:
        logger.info(f"No Blue/Green deployment found for {blue_instance}. Exiting.")
        return

    status = bgd.get_deployment_status(deployment_id)
    logger.info(f"Deployment {deployment_id} status: {status}")
    if status != 'AVAILABLE':
        logger.info(f"Deployment is not AVAILABLE (status: {status}). Waiting...")
        if not bgd.wait_for_deployment_available(deployment_id):
            logger.info(f"Deployment {deployment_id} did not become AVAILABLE. Exiting.")
            return
        target_db_instance = bgd.get_target_db_instance(deployment_id)
        target_db_status = None
        while target_db_status != 'available':
            time.sleep(60)
            target_db_status = bgd.get_rds_instance_status(target_db_instance)
            logger.info(f"Waiting for green instance {target_db_instance} — status: {target_db_status}")
        logger.info(f"Green instance {target_db_instance} is available. Proceeding with switchover.")

    # ── Get endpoint and credentials ──────────────────────────────────────────
    host, port = bgd.get_rds_instance_endpoint(blue_instance)
    logger.info(f"{blue_instance} endpoint: {host}:{port}")

    credentials_secret_name = config.get(section, 'credentials_secret_name')
    db_user, db_password = get_credentials_from_secret(credentials_secret_name, region)

    # ── Check and kill active connections ─────────────────────────────────────
    connector = dbconnector.Mysql_connector(host, port, db_user, db_password, 'INFORMATION_SCHEMA')
    output = connector.exec_query(query="select * from INFORMATION_SCHEMA.PROCESSLIST")
    if output:
        logger.info("Connection established. Active processes:")
        for i in output:
            logger.info(f"  {i}")
        for i in output:
            logger.info(f"Killing process id {i[0]}")
            connector.exec_query(query=f"kill {int(i[0])}")
            logger.info(f"Process {i[0]} killed")
    else:
        logger.info("No active processes found or connection failed — proceeding with switchover")

    # ── Trigger switchover ────────────────────────────────────────────────────
    logger.info(f"Initiating switchover for deployment {deployment_id}...")
    start_time = time.time()
    switchover_response = bgd.switchover_deployment(deployment_id)

    if not switchover_response:
        logger.info("Switchover initiation failed. Exiting.")
        return

    bgd_info = switchover_response['BlueGreenDeployment']
    logger.info(f"Deployment ID   : {bgd_info['BlueGreenDeploymentIdentifier']}")
    logger.info(f"Deployment Name : {bgd_info['BlueGreenDeploymentName']}")
    logger.info(f"Source          : {bgd_info['Source']}")
    logger.info(f"Target          : {bgd_info['Target']}")
    logger.info(f"Switchover details: {bgd_info.get('SwitchoverDetails', 'N/A')}")

    # ── Poll until SWITCHOVER_COMPLETED ───────────────────────────────────────
    while True:
        status = bgd.get_deployment_status(deployment_id)
        logger.info(f"Switchover status: {status}")
        if status == 'SWITCHOVER_COMPLETED':
            logger.info("Switchover completed successfully.")
            break
        elif status in ['FAILED', 'SWITCHOVER_FAILED']:
            logger.info(f"Switchover failed with status: {status}")
            return
        logger.info(f"Switchover in progress. Waiting 60s...")
        time.sleep(60)

    elapsed = round((time.time() - start_time) / 60, 2)
    logger.info(f"Switchover of {blue_instance} completed in {elapsed} mins.")

    # ── Post-switchover connection test ───────────────────────────────────────
    logger.info(f"Verifying connection to new instance {blue_instance} after switchover...")
    post_connector = dbconnector.Mysql_connector(host, port, db_user, db_password, 'INFORMATION_SCHEMA')
    test_result = post_connector.exec_query(query="SELECT VERSION()")
    if test_result:
        logger.info(f"Post-switchover connection test PASSED. MySQL version: {test_result[0][0]}")
    else:
        logger.info(f"Post-switchover connection test FAILED. Please check {blue_instance} status manually.")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    logger.info(f"Deleting Blue/Green deployment {deployment_id}...")
    bgd.delete_deployment(deployment_id)
    logger.info("Deployment deleted. RDS switchover process complete.")


def aurora_switchover(config, section):
    aurora_cluster = config.get(section, 'aurora_cluster')
    region         = config.get(section, 'region')
    logger         = log_writer.CustomLogger(instance_name=aurora_cluster).get_logger()
    bgd            = bgd_automation.AuroraBlueGreenDeployment(region_name=region, logger=logger)

    # ── Find AVAILABLE deployment ─────────────────────────────────────────────
    deployment_id = bgd.get_blue_green_deployment_id(aurora_cluster)
    if not deployment_id:
        logger.info(f"No Blue/Green deployment found for {aurora_cluster}. Exiting.")
        return

    status = bgd.get_deployment_status(deployment_id)
    logger.info(f"Deployment {deployment_id} status: {status}")
    if status != 'AVAILABLE':
        logger.info(f"Deployment is not AVAILABLE (status: {status}). Waiting...")
        if not bgd.wait_for_deployment_available(deployment_id):
            logger.info(f"Deployment {deployment_id} did not become AVAILABLE. Exiting.")
            return
        target_cluster = bgd.get_target_cluster(deployment_id)
        target_cluster_status = None
        while target_cluster_status != 'available':
            time.sleep(60)
            target_cluster_status = bgd.get_aurora_cluster_status(target_cluster)
            logger.info(f"Waiting for green cluster {target_cluster} — status: {target_cluster_status}")
        logger.info(f"Green cluster {target_cluster} is available. Proceeding with switchover.")

    # ── Get endpoint and credentials ──────────────────────────────────────────
    host, port = bgd.get_db_cluster_endpoint(aurora_cluster)
    logger.info(f"{aurora_cluster} endpoint: {host}:{port}")

    credentials_secret_name = config.get(section, 'credentials_secret_name')
    db_user, db_password = get_credentials_from_secret(credentials_secret_name, region)

    # ── Check and kill active connections ─────────────────────────────────────
    connector = dbconnector.Mysql_connector(host, port, db_user, db_password, 'INFORMATION_SCHEMA')
    output = connector.exec_query(query="select * from INFORMATION_SCHEMA.PROCESSLIST")
    if output:
        logger.info("Connection established. Active processes:")
        for i in output:
            logger.info(f"  {i}")
        for i in output:
            logger.info(f"Killing process id {i[0]}")
            connector.exec_query(query=f"kill {int(i[0])}")
            logger.info(f"Process {i[0]} killed")
    else:
        logger.info("No active processes found or connection failed — proceeding with switchover")

    # ── Trigger switchover ────────────────────────────────────────────────────
    logger.info(f"Initiating switchover for deployment {deployment_id}...")
    start_time = time.time()
    switchover_response = bgd.switchover_deployment(deployment_id)

    if not switchover_response:
        logger.info("Switchover initiation failed. Exiting.")
        return

    bgd_info = switchover_response['BlueGreenDeployment']
    logger.info(f"Deployment ID   : {bgd_info['BlueGreenDeploymentIdentifier']}")
    logger.info(f"Deployment Name : {bgd_info['BlueGreenDeploymentName']}")
    logger.info(f"Source          : {bgd_info['Source']}")
    logger.info(f"Target          : {bgd_info['Target']}")
    logger.info(f"Switchover details: {bgd_info.get('SwitchoverDetails', 'N/A')}")

    # ── Poll until SWITCHOVER_COMPLETED ───────────────────────────────────────
    while True:
        status = bgd.get_deployment_status(deployment_id)
        logger.info(f"Switchover status: {status}")
        if status == 'SWITCHOVER_COMPLETED':
            logger.info("Switchover completed successfully.")
            break
        elif status in ['FAILED', 'SWITCHOVER_FAILED']:
            logger.info(f"Switchover failed with status: {status}")
            return
        logger.info(f"Switchover in progress. Waiting 60s...")
        time.sleep(60)

    elapsed = round((time.time() - start_time) / 60, 2)
    logger.info(f"Switchover of {aurora_cluster} completed in {elapsed} mins.")

    # ── Post-switchover connection test ───────────────────────────────────────
    logger.info(f"Verifying connection to new cluster {aurora_cluster} after switchover...")
    post_connector = dbconnector.Mysql_connector(host, port, db_user, db_password, 'INFORMATION_SCHEMA')
    test_result = post_connector.exec_query(query="SELECT VERSION()")
    if test_result:
        logger.info(f"Post-switchover connection test PASSED. MySQL version: {test_result[0][0]}")
    else:
        logger.info(f"Post-switchover connection test FAILED. Please check {aurora_cluster} status manually.")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    logger.info(f"Deleting Blue/Green deployment {deployment_id}...")
    bgd.delete_deployment(deployment_id)
    logger.info("Deployment deleted. Aurora switchover process complete.")


def main():
    try:
        print("Starting MySQL Blue/Green switchover tool...")
        print(f"Arguments: {sys.argv}")

        config_file = sys.argv[1] if len(sys.argv) > 1 else "config.ini"
        config_file = download_s3_file(config_file)
        print(f"Local config file: {config_file}")

        if not os.path.exists(config_file):
            print(f"ERROR: Config file {config_file} not found")
            sys.exit(1)

        config = configparser.ConfigParser()
        config.read(config_file)
        sections = config.sections()
        print(f"Config sections: {sections}")

        if not sections:
            print("ERROR: No sections found in config file")
            sys.exit(1)

        for section in sections:
            print(f"Processing section: {section}")
            try:
                cluster_type            = config.get(section, 'cluster_type').lower()
                target_parameter_family = config.get(section, 'target_parameter_family').lower()

                if 'mysql' not in target_parameter_family:
                    print(f"Skipping section {section} — not MySQL")
                    continue

                if cluster_type == 'rds':
                    rds_switchover(config, section)
                elif cluster_type == 'aurora':
                    aurora_switchover(config, section)
                else:
                    print(f"Unsupported cluster_type '{cluster_type}' in section {section}")

            except Exception as e:
                print(f"ERROR in section {section}: {e}")
                continue

        print("MySQL Blue/Green switchover completed.")

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

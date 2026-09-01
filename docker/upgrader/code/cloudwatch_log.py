import boto3
import datetime,time

import logging

logger = logging.getLogger(__name__)
log_format='%(asctime)s [%(levelname)s] %(filename)s - %(message)s'
formatter = logging.Formatter(log_format)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.setLevel(logging.INFO)

 # Create RDS client
# session = boto3.Session(profile_name='<your-profile>')
# client = session.client('logs', region_name='us-east-1')
# instance_name = 'database-instance-old1'
# log_groups = [f'/aws/rds/instance/{instance_name}']


class cloudwatch_log:
    def __init__(self,region):
        # Initialize session and RDS client
        #self.session = boto3.Session(profile_name=profile)
        #self.client = self.session.client('logs', region_name=region)
        self.client =boto3.client('logs', region_name=region)
        self.filter_pattern = 'ERROR or WARN or switching or switchover or deployment'

    def log_arn(self,instance_name):
        group_arn = self.client.describe_log_groups(
                logGroupNamePattern=f'/aws/rds/instance/{instance_name}'
                # logGroupNamePrefix = '/aws/rds/instance/'
            )
        return group_arn['logGroups'][0]['arn'].replace('*','')

    def cloudwatch_live_tail(self,instance_name):
        response = self.client.start_live_tail(
                logGroupIdentifiers=[self.log_arn(instance_name)],
                logEventFilterPattern=self.filter_pattern
            )
        event_stream = response['responseStream']
        for event in event_stream:
            print(event)
            log_events = event['sessionUpdate']['sessionResults']
            for log_event in log_events:
                logger.info(log_event['logEvent']['message'])

    def get_rds_logs(self,instance_name):
        logs = self.client.get_log_events(
                logGroupName=f'/aws/rds/instance/{instance_name}/error',
                logStreamName = instance_name
            )
        # print(time.time()-10)
        for event in logs['events']:
            # print(event['message'])
            # print("event time",event['timestamp']/1000 )
            # print("utc time",int(datetime.datetime.now().timestamp()))
            if event['timestamp']/1000 > int(datetime.datetime.now().timestamp())-100:
                print(event['message'])
            else: pass
        return True

    def describe_log_streams(self,instance_name):
        logs = self.client.describe_log_streams(
                logGroupIdentifier=self.log_arn(instance_name)
            )
        return logs
class replica_log:
    def __init__(self,region):
        # Initialize session and cloudwatch client
        self.cloudwatch =boto3.client('cloudwatch', region_name=region)

    def get_rds_replica_lag(self, instance_identifier):
        try:
            # Get the ReplicaLag metric from CloudWatch
            response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName='ReplicaLag',
                Dimensions=[
                    {
                        'Name': 'DBInstanceIdentifier',
                        'Value': instance_identifier
                    }
                ],
                StartTime=time.time() - 300,  # Last 5 minutes
                EndTime=time.time(),
                Period=60,
                Statistics=['Average']
            )
            
            if response['Datapoints']:
                # Return the most recent datapoint
                return response['Datapoints'][-1]['Average']
            else:
                print(f"No replication lag data found for instance {instance_identifier}")
                return None
                
        except Exception as e:
            print(f"Error getting replication lag: {str(e)}")
            return None    

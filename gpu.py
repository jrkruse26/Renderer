import boto3
import time
import os
import subprocess

def spot_start(instancetype):

    ec2_client = boto3.client('ec2', region_name='us-east-2')
    resource = boto3.resource('ec2')
    response = ec2_client.describe_images(Owners=['self'])

    image = None
    for ami in response['Images']:
        if ami['Name'] == 'GPU Render':
            image = ami


    response = ec2_client.request_spot_instances(
        DryRun=False,
        SpotPrice='100',
        InstanceCount=1,
        Type='one-time',
        LaunchSpecification={
            'ImageId': image['ImageId'],
            'KeyName': 'GPURenderer',
            'SecurityGroups': ['Renderer'],
            'InstanceType': instancetype,
            'Placement': {
                'AvailabilityZone': 'us-east-2a',
            },
            'BlockDeviceMappings': [
                {
                    'DeviceName': "/dev/sda1",
                    'Ebs': {
                        'DeleteOnTermination': True,
                        'VolumeType': 'gp2',
                        'Encrypted': False,
                        "SnapshotId": image['BlockDeviceMappings'][0]['Ebs']['SnapshotId']
                    },
                },
            ],
            'EbsOptimized': False,
            'Monitoring': {
                'Enabled': False
            },
            'SecurityGroupIds': [
                'sg-0955161b4ce380abb',
            ]
        }
    )
    return response


def get_instances(key):
    ec2_client = boto3.client('ec2', region_name='us-east-2')
    items = ec2_client.describe_instances()
    for instance in items['Reservations']:
        if instance['Instances'][0]['State']['Name'] == 'running' and instance['Instances'][0]['KeyName'] == key:
            return instance['Instances'][0]['InstanceId']
    return None


def stop_instance():
    inst_id = get_instances('GPURenderer')
    ec2_client = boto3.client('ec2', region_name='us-east-2')
    if inst_id is not None:
            ec2_client.terminate_instances(InstanceIds=[inst_id])


ec2_client = boto3.client('ec2', region_name='us-east-2')
items = ec2_client.describe_instances()
ip = None
instance_id = None
instancetype = input('Instance Type: ')
for instance in items['Reservations']:
    if instance['Instances'][0]['State']['Name'] not in ['terminated', 'shutting-down'] and instance['Instances'][0][
        'KeyName'] == 'GPURenderer':
        instance_id = instance['Instances'][0]['InstanceId']
zone = None
if instance_id is None:
    spot_start(instancetype)
    while instance_id is None:
        instance_id = get_instances('GPURenderer')
        time.sleep(1)
    instance = ec2_client.describe_instances(InstanceIds=[instance_id])
    ip = instance['Reservations'][0]['Instances'][0][
        'PublicIpAddress']
    zone = instance['Reservations'][0]['Instances'][0]['Placement']['AvailabilityZone']
    print(ip)

price = ec2_client.describe_spot_price_history(InstanceTypes=[instancetype],MaxResults=1,ProductDescriptions=['Linux/UNIX (Amazon VPC)'],AvailabilityZone=zone)
print('Current Cost of ${}/hr'.format(price['SpotPriceHistory'][0]['SpotPrice']))

time.sleep(20)
subprocess.Popen(['C:\\Program Files (x86)\\WinSCP\\WinSCP.exe','sftp://ubuntu@{}'.format(ip), '/privatekey=C:\\Users\\Jordan\\Documents\\Renderer\\GPURenderer.ppk','/hostkey=*'])
subprocess.Popen(['C:\\Program Files\\TurboVNC\\vncviewer.exe','{}:1'.format(ip)])

input('Press Enter to Shutdown')
stop_instance()

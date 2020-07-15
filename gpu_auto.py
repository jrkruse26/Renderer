import boto3
import time
import os
import sys
import paramiko
from tkinter import Tk
from tkinter.filedialog import askopenfilenames


def spot_start(instancetype):

    ec2_client = boto3.client('ec2', region_name='us-east-2')
    resource = boto3.resource('ec2')
    response = ec2_client.describe_images(Owners=['self'])

    image = None
    for ami in response['Images']:
        if ami['Name'] == 'Auto GPU Render':
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


Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
blendfile = askopenfilenames(filetypes=[('Blender', '.blend'), ('Other', '*')])

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
start = time.time()
if instance_id is None:
    spot_start(instancetype)
    while instance_id is None:
        instance_id = get_instances('GPURenderer')
        time.sleep(1)
    instance = ec2_client.describe_instances(InstanceIds=[instance_id])
    ip = instance['Reservations'][0]['Instances'][0][
        'PublicIpAddress']
    zone = instance['Reservations'][0]['Instances'][0]['Placement']['AvailabilityZone']

price = ec2_client.describe_spot_price_history(InstanceTypes=[instancetype],MaxResults=1,ProductDescriptions=['Linux/UNIX (Amazon VPC)'],AvailabilityZone=zone)
cost = price['SpotPriceHistory'][0]['SpotPrice']
print('Current Cost of ${}/hr'.format(cost))

ssh_client = paramiko.SSHClient()
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key = paramiko.RSAKey.from_private_key_file('GPURenderer.pem')

connect = True
while connect:
    try:
        ssh_client.connect(hostname=ip, username='ubuntu', pkey=key, timeout=2)
        connect = False
        print('Connection on {}'.format(ip))
    except Exception as e:
        pass

sftp = ssh_client.open_sftp()

filenames = []
for file in blendfile:
    filename = os.path.basename(file)
    filenames.append(filename)
    print('Uploading {}'.format(filename))
    sftp.put(file, 'input/{}'.format(filename))

for file in filenames:
    print('Processing {}'.format(file))
    name = file.split('.')
    cmd = "./blender.sh \'{}\' \'{}\'".format(file, name[0])
    stdin, stdout, stderr = ssh_client.exec_command(cmd)
    stdin.close()
    for line in iter(lambda: stdout.readline(2048), ""):
        print(line, end="")

outputs = sftp.listdir('/home/ubuntu/output')
for output in outputs:
    print('Downloading {}'.format(output))
    sftp.get('/home/ubuntu/output/{}'.format(output), './outputs/{}'.format(output))

stop_instance()
print('Shutting Down')
end = time.time()
runtime = end - start
runcost = (float(runtime)/3600) * float(cost)
print('Total Run Cost of ${0:.4f}'.format(runcost))
print('Total Run Time of {} seconds'.format(runtime))
input('Press Enter to Exit')
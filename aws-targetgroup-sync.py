#!/usr/bin/env python3

import os
import re
import boto3
import click
import signal
from functools import wraps
from dotenv import load_dotenv

def one_and_only(it):
  it = iter(it)
  one = next(it)
  try:
    next(it)
  except:
    return one
  raise Exception('Expected one, got more')

_click_opt_re = re.compile(r'^--(.+)$')
def click_option_setenv(name, envvar=None, **kwargs):
  attr = _click_opt_re.match(name).group(1).replace('-', '_')
  def decorator(func):
    @click.option(name, envvar=envvar, **kwargs)
    @wraps(func)
    def wrapper(**kwargs):
      if kwargs.get(attr):
        os.environ[envvar] = kwargs[attr]
      return func(**kwargs)
    return wrapper
  return decorator

@click.command()
@click.option(
  '--target-group-name',
  envvar='AWS_SYNC_TARGET_GROUP_NAME',
  required=True,
  type=str,
  help='The AWS target group name to sync the instances with',
)
@click.option(
  '--instance-name-prefix',
  envvar='AWS_SYNC_INSTANCE_NAME_PREFIX',
  required=True,
  type=str,
  help='The AWS instance name prefix for which to assign to the target group',
)
@click.option(
  '--instance-port',
  envvar='AWS_SYNC_INSTANCE_PORT',
  required=True,
  type=int,
  help='The port on the instances to associate with the target group',
)
@click.option(
  '--sleep',
  envvar='AWS_SYNC_SLEEP',
  default=False,
  type=bool,
  is_flag=True,
  help='Whether or not to sleep forever after execution',
)
@click.option(
  '--dry-run',
  envvar='AWS_SYNC_DRY_RUN',
  default=False,
  type=bool,
  is_flag=True,
  help='Perform checks but do not make any changes',
)
@click_option_setenv(
  '--aws-default-region',
  envvar='AWS_DEFAULT_REGION',
  required=False,
  help='AWS Configuration: Default Region',
)
@click_option_setenv(
  '--aws-access-key-id',
  envvar='AWS_ACCESS_KEY_ID',
  required=False,
  help='AWS Configuration: IAM Access Key ID',
)
@click_option_setenv(
  '--aws-secret-access-key',
  envvar='AWS_SECRET_ACCESS_KEY',
  required=False,
  help='AWS Configuration: IAM Secret Access Key',
)
def sync(target_group_name, instance_name_prefix, instance_port, sleep, dry_run, **kwargs):
  ec2 = boto3.client('ec2')
  elbv2 = boto3.client('elbv2')

  syncable_instance_selector = dict(
    Filters=[
      dict(
        Name='tag:Name',
        Values=[f"{instance_name_prefix}*"],
      ),
      dict(
        Name='instance-state-name',
        Values=['running'],
      ),
    ]
  )
  target_group_selector = dict(
    Names=[target_group_name],
  )
  #
  # Step 0 -- detect node change & execute the following (TODO)
  #
  current_instances = {}
  current_target_groups = {}
  #
  # Step 1 -- find nodes
  instances = ec2.describe_instances(**syncable_instance_selector)
  for reservation in instances['Reservations']:
    for instance in reservation['Instances']:
      current_instances[instance['InstanceId']] = instance
  #
  # Step 2 -- find target groups
  target_groups = elbv2.describe_target_groups(**target_group_selector)
  for target_group in target_groups['TargetGroups']:
    current_target_groups[target_group['TargetGroupArn']] = set()
    target_group_health = elbv2.describe_target_health(
      TargetGroupArn=target_group['TargetGroupArn']
    )
    for target_health_description in target_group_health['TargetHealthDescriptions']:
      current_target_groups[target_group['TargetGroupArn']].add(target_health_description['Target']['Id'])
  #
  # Step 3 -- sync single target group with instances
  target_group_id, target_group_instance_ids = one_and_only(current_target_groups.items())
  print('current', target_group_id, target_group_instance_ids)
  #
  to_add = current_instances.keys() - target_group_instance_ids
  to_remove = target_group_instance_ids - current_instances.keys()
  for instance_id in to_add:
    print('adding', instance_id, 'to', target_group_id)
    if not dry_run:
      elbv2.register_targets(
        TargetGroupArn=target_group_id,
        Targets=[
          dict(
            Id=instance_id,
            Port=instance_port,
          )
        ]
      )
  for instance_id in to_remove:
    print('removing', instance_id, 'from', target_group_id)
    if not dry_run:
      elbv2.deregister_targets(
        TargetGroupArn=target_group_id,
        Targets=[
          dict(
            Id=instance_id,
            Port=instance_port,
          )
        ]
      )
  #
  if sleep:
    click.echo('sleeping forever...')
    if not dry_run:
      signal.pause()

if __name__ == '__main__':
  load_dotenv()
  sync()

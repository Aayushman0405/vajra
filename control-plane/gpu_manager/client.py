"""
AWS GPU Manager for Vajra - On-demand GPU instances
"""
import boto3
import time
import asyncio
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from config import settings


class AWSGPUManager:
    def __init__(self):
        self.region = settings.aws_region

        self.ec2 = boto3.client(
            "ec2",
            region_name=self.region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

        self.ecr_client = boto3.client(
            "ecr",
            region_name=self.region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

        # Config
        self.instance_type = settings.aws_gpu_instance_type
        self.ami_id = settings.aws_gpu_ami
        self.key_name = settings.aws_key_name
        self.security_group_id = settings.aws_security_group_id
        self.subnet_id = settings.aws_subnet_id

        self.instance_id: Optional[str] = None
        self.instance_ip: Optional[str] = None
        self.last_request_time: Optional[datetime] = None
        self.request_count = 0
        self.idle_timeout_minutes = 5

        self._start_idle_checker()

    def _start_idle_checker(self):
        async def check_idle():
            while True:
                await asyncio.sleep(60)
                await self._check_idle_shutdown()

        asyncio.create_task(check_idle())

    async def _check_idle_shutdown(self):
        if self.instance_id and self.last_request_time:
            idle_time = datetime.utcnow() - self.last_request_time
            if idle_time > timedelta(minutes=self.idle_timeout_minutes):
                print(f"⏰ Shutting down idle instance {self.instance_id}")
                await self.shutdown_instance()

    async def ensure_gpu_running(self) -> bool:
        if self.instance_id:
            try:
                response = self.ec2.describe_instances(
                    InstanceIds=[self.instance_id]
                )
                state = response["Reservations"][0]["Instances"][0]["State"]["Name"]

                if state == "running":
                    return True
                elif state == "stopped":
                    self.ec2.start_instances(InstanceIds=[self.instance_id])
                    await self._wait_for_instance_running()
                    return True
            except Exception:
                self.instance_id = None

        return await self._launch_instance()

    async def _launch_instance(self) -> bool:
        try:
            # ECR login token
            auth = self.ecr_client.get_authorization_token()
            proxy = auth["authorizationData"][0]["proxyEndpoint"]

            user_data = f"""#!/bin/bash
apt-get update
apt-get install -y docker.io awscli

systemctl start docker

aws ecr get-login-password --region {self.region} | \
docker login --username AWS --password-stdin {proxy}

docker run -d --gpus all \
    -p 8000:8000 \
    -e HF_TOKEN={settings.hf_token} \
    {settings.aws_ecr_repository}:latest
"""

            response = self.ec2.run_instances(
                ImageId=self.ami_id,
                InstanceType=self.instance_type,
                KeyName=self.key_name,
                SecurityGroupIds=[self.security_group_id],
                SubnetId=self.subnet_id,
                MinCount=1,
                MaxCount=1,
                UserData=user_data,
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": "vajra-gpu-node"},
                            {"Key": "Project", "Value": "vajra"},
                        ],
                    }
                ],
            )

            self.instance_id = response["Instances"][0]["InstanceId"]
            print(f"🚀 Launched GPU instance: {self.instance_id}")

            await self._wait_for_instance_running()

            waiter = self.ec2.get_waiter("instance_status_ok")
            waiter.wait(InstanceIds=[self.instance_id])

            info = self.ec2.describe_instances(InstanceIds=[self.instance_id])
            self.instance_ip = info["Reservations"][0]["Instances"][0][
                "PublicIpAddress"
            ]

            await self._wait_for_container_ready()
            return True

        except Exception as e:
            print(f"❌ Launch failed: {e}")
            return False

    async def _wait_for_instance_running(self):
        while True:
            response = self.ec2.describe_instances(
                InstanceIds=[self.instance_id]
            )
            state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
            if state == "running":
                break
            await asyncio.sleep(5)

    async def _wait_for_container_ready(self):
        for _ in range(30):
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(
                        f"http://{self.instance_ip}:8000/health", timeout=5
                    )
                    if r.status_code == 200:
                        print("✅ GPU container ready")
                        return
            except:
                pass
            await asyncio.sleep(10)

        raise Exception("GPU container failed to start")

    async def shutdown_instance(self):
        if self.instance_id:
            self.ec2.stop_instances(InstanceIds=[self.instance_id])
            waiter = self.ec2.get_waiter("instance_stopped")
            waiter.wait(InstanceIds=[self.instance_id])
            print(f"🛑 Stopped instance {self.instance_id}")
            self.instance_id = None
            self.instance_ip = None
            self.last_request_time = None
        return True

    async def terminate_instance(self):
        """Terminate the GPU instance completely (not just stop)"""
        if self.instance_id:
            try:
                self.ec2.terminate_instances(InstanceIds=[self.instance_id])
                print(f"🗑️ Terminated GPU instance: {self.instance_id}")
                self.instance_id = None
                self.instance_ip = None
                return True
            except Exception as e:
                print(f"⚠️ Failed to terminate: {e}")
                return False
        return True

    async def health_check(self) -> Dict[str, Any]:
        """Check if GPU instance is healthy"""
        if self.instance_id and self.instance_ip:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"http://{self.instance_ip}:8000/health")
                    if response.status_code == 200:
                        return {"status": "healthy", "details": response.json()}
            except:
                pass
        return {"status": "unhealthy", "details": "No running instance"}

# Singleton instance
aws_gpu_manager = AWSGPUManager()

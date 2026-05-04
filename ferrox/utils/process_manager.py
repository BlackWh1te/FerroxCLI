"""Background Process Manager for Ferrox - Devin-parity feature"""

import asyncio
import os
import shlex
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class BackgroundJob:
    """Represents a background job"""

    pid: int
    command: str
    process: asyncio.subprocess.Process
    start_time: datetime
    log_file: str
    cwd: str = "."
    status: str = "running"  # running, completed, failed


class ProcessManager:
    """
    Singleton ProcessManager for tracking background jobs.
    Allows non-blocking execution of long-running tasks (servers, watchers).
    """

    _instance = None
    jobs: dict[int, BackgroundJob] = field(default_factory=dict)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.jobs = {}
        return cls._instance

    async def start_job(self, command: str, cwd: str = ".") -> BackgroundJob:
        """Start a background process and return its job object."""
        log_dir = Path.home() / ".ferrox" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        cmd_parts = shlex.split(command)
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        log_file = str(log_dir / f"job_{proc.pid}.log")

        job = BackgroundJob(
            pid=proc.pid,
            command=command,
            process=proc,
            start_time=datetime.now(),
            log_file=log_file,
            cwd=cwd,
            status="running",
        )

        self.jobs[proc.pid] = job

        # Start logging task
        asyncio.create_task(self._stream_logs(job))

        return job

    async def _stream_logs(self, job: BackgroundJob):
        """Continuously stream stdout/stderr to a log file."""
        try:
            with open(job.log_file, "w") as f:
                f.write(f"=== Job {job.pid} started at {job.start_time} ===\n")
                f.write(f"Command: {job.command}\n")
                f.write(f"CWD: {job.cwd}\n")
                f.write("=" * 50 + "\n\n")

                # Read stdout
                while True:
                    if job.process.stdout is None:
                        break
                    try:
                        line = await asyncio.wait_for(job.process.stdout.readline(), timeout=1.0)
                        if not line:
                            break
                        f.write(f"[STDOUT] {line.decode()}")
                        f.flush()
                    except asyncio.TimeoutError:
                        # Check if process is done
                        if job.process.returncode is not None:
                            break
                        continue

                # Read stderr
                if job.process.stderr:
                    while True:
                        try:
                            line = await asyncio.wait_for(
                                job.process.stderr.readline(), timeout=1.0
                            )
                            if not line:
                                break
                            f.write(f"[STDERR] {line.decode()}")
                            f.flush()
                        except asyncio.TimeoutError:
                            if job.process.returncode is not None:
                                break
                            continue

                # Update status
                returncode = job.process.returncode
                if returncode == 0:
                    job.status = "completed"
                else:
                    job.status = "failed"

                f.write(f"\n=== Job finished with exit code: {returncode} ===\n")

        except Exception as e:
            job.status = "failed"
            print(f"Log error for job {job.pid}: {e}")

    async def get_job_status(self, pid: int) -> dict:
        """Get status of a specific job."""
        if pid not in self.jobs:
            return {"status": "not_found", "pid": pid}

        job = self.jobs[pid]

        # Check if still running
        if job.process.returncode is None:
            job.status = "running"
        elif job.process.returncode == 0:
            job.status = "completed"
        else:
            job.status = "failed"

        return {
            "pid": pid,
            "command": job.command,
            "status": job.status,
            "start_time": job.start_time.isoformat(),
            "log_file": job.log_file,
            "cwd": job.cwd,
            "exit_code": job.process.returncode,
        }

    async def kill_job(self, pid: int) -> dict:
        """Kill a background job."""
        if pid not in self.jobs:
            return {"success": False, "error": f"Job {pid} not found"}

        job = self.jobs[pid]

        try:
            job.process.kill()
            job.status = "killed"
            return {"success": True, "pid": pid, "message": f"Job {pid} terminated"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_jobs(self) -> list[dict]:
        """List all background jobs."""
        result = []
        for pid, _job in self.jobs.items():
            status = await self.get_job_status(pid)
            result.append(status)
        return result

    async def get_job_logs(self, pid: int, lines: int = 100) -> str:
        """Get last N lines of job logs."""
        if pid not in self.jobs:
            return f"Job {pid} not found"

        job = self.jobs[pid]

        if not os.path.exists(job.log_file):
            return "Log file not found"

        try:
            with open(job.log_file) as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except Exception as e:
            return f"Error reading logs: {e}"

    async def cleanup_completed(self):
        """Remove completed/failed jobs from tracking."""
        completed = []
        for pid, job in self.jobs.items():
            if job.process.returncode is not None:
                completed.append(pid)

        for pid in completed:
            del self.jobs[pid]

        return len(completed)

    def get_job_count(self) -> int:
        """Get count of active jobs."""
        return sum(1 for job in self.jobs.values() if job.process.returncode is None)


# Global instance
process_manager = ProcessManager()

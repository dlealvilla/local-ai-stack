from adapters.executor.docker import DockerExecutor
from core.executor import ProcessExecutor


EXECUTORS = {
    "process": ProcessExecutor,
    "docker": DockerExecutor,
}


def get_executor(name):
    executor_class = EXECUTORS.get(name)

    if executor_class is None:
        raise ValueError(
            f"Unsupported runtime executor: {name}"
        )

    return executor_class()

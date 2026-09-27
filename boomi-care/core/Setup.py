import os
from enum import Enum
from dotenv import load_dotenv


class Singleton (type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class Setup(metaclass=Singleton):
    """
    Setup for solution
    """

    def __init__(self, env_files: list[str]):
        """Define setting for testing

        :param env_file:  list of *.env files, first valid file will be
                                used e.g. ["private.env", "public.env"]
        """
        # set variables based on environment files
        for env_file in env_files:
            if os.path.isfile(env_file):
                load_dotenv(env_file)
                break


import asyncio
from asyncio import Event, create_task, wait
from dataclasses import dataclass
from functools import wraps
import logging
from pathlib import Path
import re
import signal
import subprocess
import typer
from typing_extensions import Annotated
import urllib
import urllib.parse


class SynchronizationError(Exception):
    pass


@dataclass
class Config:
    branch: str | None
    dest: Path | None
    url: urllib.parse.ParseResult


class Synchronizer:
    def __init__(self, config: Config):
        self.config = config
        self.shutdown = Event()

    async def run(self, delay: int):
        shutdown = create_task(self.shutdown.wait())
        while True:
            self.sync()
            _ = await wait(
                [shutdown],
                timeout=delay,
            )
            if self.shutdown.is_set():
                break

    def stop(self):
        logging.debug("stopping synchronizer")
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(self.shutdown.set)

    def sync(self):
        if self.config.dest is None:
            match = re.search(r"([^/]+)$", self.config.url.path)
            if not match:
                raise SynchronizationError(
                    f"failed to determine repository name from url path: {self.config.url.path}"
                )
            dest = Path(match.group(1).removesuffix(".git"))
        else:
            dest = self.config.dest
        if dest.is_dir():
            if self.config.branch is None:
                logging.debug("getting current branch")
                branch = self.__git(["rev-parse", "--abbrev-ref", "HEAD"], dest)
            else:
                branch = self.config.branch
            logging.debug(f"fetching origin/{branch}")
            self.__git(["fetch", "origin", branch], dest)
            logging.debug(f"checking out {branch}")
            self.__git(["checkout", branch], dest)
            logging.debug(f"rebasing from origin/{branch}")
            self.__git(["rebase", "origin", branch], dest)
        else:
            opts = ["--depth", "1", "--single-branch"]
            if self.config.branch is not None:
                opts += ["-b", self.config.branch]
            logging.debug(f"cloning into {dest}")
            self.__git(["clone"] + opts + [self.config.url.geturl(), dest])
        logging.info("repository synchronized")

    def __git(self, args: list[str], dir: Path | None = None) -> str:
        opts = []
        if dir is not None:
            opts = ["-C", dir]
        process = subprocess.Popen(
            args=["git"] + opts + args,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout, stderr = process.communicate()
        stdout = stdout.decode().strip()
        log_lvl = logging.getLogger().getEffectiveLevel()
        if log_lvl <= logging.DEBUG:
            for line in stdout.splitlines():
                logging.debug(f"git: {line}")
            if process.returncode == 0:
                stderr = stderr.decode().strip()
                for line in stderr.splitlines():
                    logging.debug(f"git: {line}")
        if process.returncode != 0:
            stderr = stderr.decode().strip()
            for line in stderr.splitlines():
                logging.error(f"git: {line}")
            raise SynchronizationError("git failed")
        return stdout


def shutdown(signum: int, synchronizer: Synchronizer):
    logging.debug(f"signal {signum} received, shutting down")
    synchronizer.stop()


def typer_async(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


def validate_password(
    ctx: typer.Context, param: typer.CallbackParam, value: str
) -> str:
    if ctx.params.get("user") and not value:
        raise typer.BadParameter("password is required if user is defined")
    return value


def validate_user(ctx: typer.Context, param: typer.CallbackParam, value: str) -> str:
    if ctx.params.get("password") and not value:
        raise typer.BadParameter("user is required if password is defined")
    return value


@typer_async
async def git_sync(
    url: Annotated[
        str, typer.Argument(help="URL to the repository", envvar="REPO_URL")
    ],
    dest: Annotated[
        Path,
        typer.Option(
            "-d",
            "--destination",
            help="Path to destination directory",
            envvar="DESTINATION",
        ),
    ] = None,
    branch: Annotated[
        Path, typer.Option("-b", "--branch", help="Branch", envvar="REPO_BRANCH")
    ] = None,
    once: Annotated[
        bool,
        typer.Option("-o", "--once", help="Just run once and exit", envvar="RUN_ONCE"),
    ] = False,
    password: Annotated[
        str,
        typer.Option(
            "-p",
            "--password",
            help="Password (only used with HTTP)",
            envvar="REPO_PASSWORD",
            callback=validate_password,
        ),
    ] = None,
    user: Annotated[
        str,
        typer.Option(
            "-u",
            "--user",
            help="Username (only used with HTTP)",
            envvar="REPO_USER",
            callback=validate_user,
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", envvar="VERBOSE", help="Increase verbosity"),
    ] = False,
    watch_delay: Annotated[
        int,
        typer.Option(
            "--watch-delay",
            help="Number of seconds to wait between two pull if watch is enabled",
            envvar="WATCH_DELAY",
        ),
    ] = 30,
):
    log_lvl = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_lvl)
    url = urllib.parse.urlparse(url)
    if url.scheme.startswith("http") and user and password:
        authority = f"{user}:{password}@{url.netloc}"
        url = url._replace(netloc=authority)
    config = Config(
        branch=branch,
        dest=dest,
        url=url,
    )
    synchronizer = Synchronizer(config)
    try:
        if once:
            synchronizer.sync()
        else:
            signal.signal(
                signal.SIGTERM, lambda signum, _: shutdown(signum, synchronizer)
            )
            signal.signal(
                signal.SIGINT, lambda signum, _: shutdown(signum, synchronizer)
            )
            await synchronizer.run(watch_delay)
    except SynchronizationError as err:
        logging.error(err)
        exit(1)


def main():
    typer.run(git_sync)

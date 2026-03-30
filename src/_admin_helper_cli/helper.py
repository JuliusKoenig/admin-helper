import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Sequence

from jinja2 import Template


def render(logger: logging.Logger,
           src: Path,
           dst: Path,
           cleanup: bool = False,
           **kwargs):
    
    logger.debug(f"Rendering templates from {src} to {dst} with cleanup={cleanup}")
    
    if dst.is_dir():
        if cleanup:
            logger.debug(f"Cleaning up {dst}")
            shutil.rmtree(dst)
        else:
            logger.debug(f"{dst} already exists, leaving it as is")
    dst.mkdir(parents=True, exist_ok=True)

    template_paths = []
    for root, _, files in src.walk():
        for f in files:
            if not f.endswith(".j2"):
                continue
            template_paths.append(Path(root / f).relative_to(src))

    for template_path in template_paths:
        src_path = src / template_path
        dst_path = dst / template_path.with_suffix("")
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with open(src_path, "r") as f:
            template = Template(f.read())
        output = template.render(**kwargs)
        with open(dst_path, "w") as f:
            f.write(output)
        logger.debug(f"Rendered {src_path} to {dst_path}")
        
        
def run_cmd(logger: logging.Logger,
            args: Sequence[str],
            cwd: Path | None = None) -> None:
    if cwd is None:
        cwd = Path.cwd()
    logger.debug(f"Running command: \"{' '.join(args)}\" in {cwd}")
    result = subprocess.run(args, 
                   cwd=cwd, 
                   stdout=sys.stdout, 
                   stderr=sys.stderr,
                   check=True)
    if result.returncode != 0:
        logger.error(f"Command \"{' '.join(args)}\" failed with return code {result.returncode}")
    else:       
        logger.debug(f"Command \"{' '.join(args)}\" finished successfully with return code {result.returncode}")
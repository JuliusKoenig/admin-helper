from pathlib import Path
import shutil

from admin_helper_cli.logger import logger
from admin_helper_cli.settings import settings


WORK_PATH = Path("cli/src/admin_helper_cli/modules/traefik")
SRC_PATH = WORK_PATH / "templates"
DST_PATH = WORK_PATH / "output"


def render(src: Path, dst: Path, overwrite: bool = True):
    if dst.is_dir():
        if not overwrite:
            logger.debug(f"Output directory {dst} already exists. Skipping rendering.")
            return
        logger.debug(f"Output directory {dst} already exists. Removing it for fresh rendering.")
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    template_paths = []
    
    def walk(_src):
        for root, dirs, files in _src.walk():
            for d in dirs:
                result = walk(_src / d)
                print
            print
    
    result = walk(src)
    print()        
    
    for template in src.glob("*.j2"):
        print()
    #     with open(template, "r") as f:
    #         content = f.read()
    #     content = content.replace("{{ TRAEFIK_BINARY_PATH }}", str(settings.traefik.binary_path))
    #     output_file = dst / template.with_suffix("").name
    #     with open(output_file, "w") as f:
    #         f.write(content)
    #     logger.debug(f"Rendered {template} to {output_file}")
    

if __name__ == "__main__":
    render(src=SRC_PATH, dst=DST_PATH)
    print()
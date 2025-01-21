import pytest
import os.path


def test_readme():
    # not the cleanest way of testing code blocks in the README file

    readme_file = os.path.realpath(os.path.join(__file__, "../../README.md"))
    with open(readme_file, "r") as f:
        lines = f.readlines()

    python_code_blocks = []
    code_block = ""
    active_block = False
    for line in lines:
        if line.strip() == "```python":
            active_block = True
            continue
        elif line.strip() == "```":
            active_block = False
            if code_block:
                python_code_blocks.append(code_block)
            code_block = ""
            continue
        if active_block:
            code_block += line

    for code in python_code_blocks:
        indented_code = "    " + code.replace("\n", "\n    ")
        wrapper = (
            "import asyncio"
            + "\n"
            + "async def main():\n"
            + indented_code
            + "\n"
            + "asyncio.run(main())"
        )
        print(wrapper)
        exec(wrapper)

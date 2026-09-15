"""file_ops 基础文件工具单元测试。"""

from pathlib import Path
import pytest

from tools.builtin.file_ops import (
    ViewFileTool,
    FileWriteTool,
    _resolve_within_root,
)


def test_resolve_within_root_normal_and_escape(tmp_path: Path):
    """测试工作区根目录路径解析与防越界校验。"""
    root = tmp_path.resolve()

    # 正常相对路径
    p1 = _resolve_within_root("src/main.py", root)
    assert p1 == root / "src" / "main.py"

    # 包含相对跳转但仍在工作区内部
    p2 = _resolve_within_root("src/../src/main.py", root)
    assert p2 == root / "src" / "main.py"

    # 越界路径：跳出 root
    with pytest.raises(PermissionError, match="路径越出工作区根目录"):
        _resolve_within_root("../../etc/passwd", root)

    # 绝对路径但不在 root 内部
    with pytest.raises(PermissionError, match="路径越出工作区根目录"):
        _resolve_within_root("/etc/hosts", root)


@pytest.mark.asyncio
async def test_file_write_and_view_tool(tmp_path: Path):
    """测试写入文件并带行号读取。"""
    root_str = str(tmp_path)
    writer = FileWriteTool(workspace_root=root_str)
    viewer = ViewFileTool(workspace_root=root_str)

    # 1. 写入多行文件（自动创建嵌套目录）
    content = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    write_res = await writer.invoke({
        "path": "sub/dir/test.txt",
        "content": content,
    })
    assert write_res.ok is True
    assert (tmp_path / "sub/dir/test.txt").is_file()

    # 2. 读取特定行范围 (line 2 到 line 4)
    view_res = await viewer.invoke({
        "path": "sub/dir/test.txt",
        "start_line": 2,
        "end_line": 4,
    })
    assert view_res.ok is True
    output = view_res.content
    assert "2\tline 2" in output
    assert "3\tline 3" in output
    assert "4\tline 4" in output
    assert "1\tline 1" not in output


@pytest.mark.asyncio
async def test_file_ops_escape_protection(tmp_path: Path):
    """测试工具层拒绝越界操作。"""
    root_str = str(tmp_path)
    writer = FileWriteTool(workspace_root=root_str)
    viewer = ViewFileTool(workspace_root=root_str)

    # 尝试读取越界文件
    view_res = await viewer.invoke({"path": "../outside.txt"})
    assert view_res.ok is False
    assert "路径越出工作区根目录" in view_res.content

    # 尝试写入越界文件
    write_res = await writer.invoke({"path": "../outside.txt", "content": "bad"})
    assert write_res.ok is False
    assert "路径越出工作区根目录" in write_res.content

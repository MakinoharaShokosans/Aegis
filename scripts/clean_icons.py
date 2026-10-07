#!/usr/bin/env python3
"""清洗仓库文档中所有 emoji / icon 符号脚本。

去除标题、表格、列表、目录树中具有 AI 痕迹的 decorative icons，保持工业级技术文档严谨规范。
"""

import re
from pathlib import Path

# 定义待处理文件范围
TARGET_PATHS = [
    Path("README.md"),
    *Path("documents").rglob("*.md"),
]

# Emoji Unicode 范围正则
EMOJI_REGEX = re.compile(
    r"[\U00010000-\U0010ffff"  # 补充符号表、象形文字、表情等
    r"\u2600-\u27bf"           # 杂项符号、Dingbats
    r"\u2300-\u23ff"           # 杂项技术符号 (如 ⏱ 等)
    r"\u2b50\u2b55"            # 星号、圆圈
    r"\ufe0e\ufe0f"            # 变体选择符
    r"\u200d"                  # 零宽连字
    r"]",
    flags=re.UNICODE
)

def clean_content(text: str) -> str:
    # 1. 箭头与特殊符号标准化
    text = text.replace("➔", "->")
    text = text.replace("★", "*")
    
    # 2. 状态标签标准化
    text = text.replace("✅ **PASSED**", "**PASSED**")
    text = text.replace("✅ PASSED", "PASSED")
    text = text.replace("✅ PASS", "PASS")
    text = text.replace("✅", "[x]")
    text = text.replace("🚫 拒绝注册", "拒绝注册")
    text = text.replace("🚫", "[已拦截]")
    
    # 3. 清理 Markdown 结构标记紧随的 Emoji 与多余空格
    # Headers: ## 📁 Title -> ## Title
    text = re.sub(r"^(#+\s*)" + EMOJI_REGEX.pattern + r"+\s*", r"\1", text, flags=re.MULTILINE)
    # List items: • 🧠 Title -> • Title, - 🧠 Title -> - Title
    text = re.sub(r"^(\s*[-*•]\s*)" + EMOJI_REGEX.pattern + r"+\s*", r"\1", text, flags=re.MULTILINE)
    # Table cells: | 🛍️ [Title] -> | [Title], | 🤖 [Title] -> | [Title]
    text = re.sub(r"(\|\s*)" + EMOJI_REGEX.pattern + r"+\s*", r"\1", text)
    # Tree comments: # 👑 【Title】 -> # 【Title】
    text = re.sub(r"(#\s*)" + EMOJI_REGEX.pattern + r"+\s*", r"\1", text)
    # Quotes: > 🌟 Title -> > Title
    text = re.sub(r"^(>\s*)" + EMOJI_REGEX.pattern + r"+\s*", r"\1", text, flags=re.MULTILINE)
    
    # 4. 全局清理剩余所有纯装饰 Emoji
    text = EMOJI_REGEX.sub("", text)
    
    # 5. 清理多余空格但保留代码缩进与表格对齐基本结构
    # 将多个连续行内空格（非行首缩进）收敛
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        # 去除行尾空白
        rstripped = line.rstrip()
        # 清理形如 "##  Title" 为 "## Title"
        header_cleaned = re.sub(r"^(#+)\s{2,}", r"\1 ", rstripped)
        cleaned_lines.append(header_cleaned)
    
    return "\n".join(cleaned_lines)

def main():
    modified_count = 0
    for p in TARGET_PATHS:
        if not p.is_file():
            continue
        original = p.read_text(encoding="utf-8")
        cleaned = clean_content(original)
        if cleaned != original:
            p.write_text(cleaned, encoding="utf-8")
            modified_count += 1
            print(f"[CLEANED] {p}")
            
    print(f"\n全部文档清洗完成，共修改 {modified_count} 个文档。")

if __name__ == "__main__":
    main()

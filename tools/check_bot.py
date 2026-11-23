#!/usr/bin/env python3
"""Check the bot mod against the project's code rules before a commit.

    tools/check_bot.py [MOD_DIR]      (default: bot/)

- every .js file parses (node --check, ES module or script);
- no comments in the bot's JS except references to the specification,
  `// spec FILE §N` (AGENTS.md, Code), where spec/FILE.md exists and has a
  section N. Detection is a small JS lexer that skips string, template
  and regular-expression literals, so `//` inside a string is not a
  comment.

Exit status 1 when a rule is broken, with file:line for each finding.
"""
import os
import re
import subprocess
import sys

REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^") | {""}
REGEX_WORDS = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case", "do",
               "else", "yield", "await"}


def comments(src):
    """Yield (line, text) for each comment in JS source."""
    i, n, line = 0, len(src), 1
    prev = ""
    word = ""
    stack = []  # template literal nesting: brace depth inside ${ }
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
        if c in " \t\r\n":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            yield line, src[i:j]
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            yield line, src[i:j].split("\n")[0]
            line += src.count("\n", i, j)
            i = j
            continue
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            line += src.count("\n", i, j)
            i, prev, word = j + 1, "x", ""
            continue
        if c == "`" or (c == "}" and stack and stack[-1] == 0):
            if c == "}":
                stack.pop()
            j = i + 1
            while j < n and src[j] != "`":
                if src[j] == "\\":
                    j += 2
                    continue
                if src.startswith("${", j):
                    stack.append(0)
                    j += 2
                    break
                j += 1
            else:
                line += src.count("\n", i, j)
                i, prev, word = j + 1, "x", ""
                continue
            line += src.count("\n", i, j)
            i, prev, word = j, "(", ""
            continue
        if c == "{" and stack:
            stack[-1] += 1
        elif c == "}" and stack:
            stack[-1] -= 1
        if c == "/" and (prev in REGEX_PREV or word in REGEX_WORDS):
            j, cls = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    cls = True
                elif src[j] == "]":
                    cls = False
                elif src[j] == "/" and not cls:
                    break
                j += 1
            j += 1
            while j < n and src[j].isalpha():
                j += 1
            i, prev, word = j, "x", ""
            continue
        m = re.match(r"[A-Za-z_$][\w$]*", src[i:i + 64])
        if m:
            word = m.group(0)
            prev = "x"
            i += len(word)
            continue
        word = ""
        prev = c if c in REGEX_PREV else "x"
        i += 1


SPEC_REF = re.compile(r"^// spec ([a-z0-9-]+) §(\d+)$")


def spec_reference_error(repo, text):
    """None when the comment is a valid reference to a section of spec/, else why not."""
    m = SPEC_REF.match(text.strip())
    if not m:
        return "comment"
    path = os.path.join(repo, "spec", m.group(1) + ".md")
    if not os.path.isfile(path):
        return f"reference to a missing spec/{m.group(1)}.md"
    with open(path, encoding="utf-8") as fh:
        if not re.search(rf"^## {m.group(2)}\. ", fh.read(), re.M):
            return f"reference to a missing section {m.group(2)} of spec/{m.group(1)}.md"
    return None


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mod = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(repo, "bot")
    if not os.path.isdir(mod):
        sys.exit(f"check_bot.py: no {mod}")
    bad = 0
    for root, _, files in sorted(os.walk(mod)):
        for f in sorted(files):
            if not f.endswith(".js"):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, repo)
            with open(p, encoding="utf-8") as fh:
                src = fh.read()
            ok = any(subprocess.run(["node", f"--input-type={m}", "--check"], input=src.encode(),
                                    capture_output=True).returncode == 0 for m in ("module", "commonjs"))
            if not ok:
                bad += 1
                print(f"{rel}: does not parse (node --check)")
            for line, text in comments(src):
                why = spec_reference_error(repo, text)
                if why:
                    bad += 1
                    print(f"{rel}:{line}: {why}: {text[:80]}")
    if bad:
        print(f"check_bot.py: {bad} finding(s)")
        sys.exit(1)
    print(f"check_bot.py: {mod} OK")


if __name__ == "__main__":
    main()

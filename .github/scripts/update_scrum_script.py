import os
import re
from github import Github

# ---------------------------------------------------------
# 0. 설정: GitHub 로그인 -> 템플릿에 쓰는 이름(표기명) 매핑
#    필요하면 여기만 팀에 맞게 바꾸면 됩니다.
# ---------------------------------------------------------
USER_MAP = {
    # "githubLogin": "TemplateName"
    "Hwanvely": "Leo",
    "dragonwaterr": "Robin",
    "epdlrnldudnj": "Ray",
    "Leejeonglim": "Kiel",
    "king0104": "Freddie",
    "som0309": "Ann",
}

AGENDA_TYPES = {"오늘 할 일", "예상되는 이슈", "작일 회고"}

SECTION_1_TITLE = "## 1. 아젠다/결과/피드백"
SECTION_2_TITLE = "## 2. Will do (누가 언제까지 무엇을)"
SECTION_3_TITLE = "## 3. TBD (논의가 완료되지 않은 아젠다)"



token = os.environ["GITHUB_TOKEN"]
repo_name = os.environ["REPO_NAME"]
issue_number = int(os.environ["ISSUE_NUMBER"])
comment_body = os.environ.get("COMMENT_BODY", "")
comment_author_login = os.environ.get("COMMENT_AUTHOR", "")
comment_author_type = os.environ.get("COMMENT_AUTHOR_TYPE", "")


if (comment_author_type or "").lower() == "bot":
    print("ℹ️ Bot comment ignored.")
    raise SystemExit(0)

author_name = USER_MAP.get(comment_author_login, comment_author_login)



g = Github(token)
repo = g.get_repo(repo_name)
issue = repo.get_issue(number=issue_number)
body = issue.body or ""



def clean_text(text: str) -> str:

    if not text:
        return "-"
    t = text.strip()
    if not t:
        return "-"
    return t.replace("\r\n", "<br>").replace("\n", "<br>")


def extract_mentions(text: str) -> str:
    
    mentions = re.findall(r"@([a-zA-Z0-9-]+)", text)
    return ", ".join(mentions) if mentions else "-"


def parse_command(text: str):
    
    t = (text or "").strip()

    if t.startswith("/willdo"):
        payload = t[len("/willdo"):].strip()
        parts = [p.strip() for p in payload.split("|")]
        what = parts[0] if len(parts) > 0 else ""
        goal = parts[1] if len(parts) > 1 else ""
        due = parts[2] if len(parts) > 2 else ""
        return ("willdo", what, goal, due)

    if t.startswith("/tbd"):
        payload = t[len("/tbd"):].strip()
        parts = [p.strip() for p in payload.split("|")]
        content = parts[0] if len(parts) > 0 else ""
        note = parts[1] if len(parts) > 1 else ""
        kind = parts[2] if len(parts) > 2 else ""
        dm = parts[3] if len(parts) > 3 else ""
        discuss = parts[4] if len(parts) > 4 else ""
        return ("tbd", content, note, kind, dm, discuss)

    return (None,)


def replace_in_section(full_body: str, section_title: str, replacer_fn):
    
    pattern = rf"({re.escape(section_title)}\s*\n)([\s\S]*?)(?=\n##\s|\Z)"
    m = re.search(pattern, full_body)
    if not m:
        return full_body, False

    header = m.group(1)
    section = m.group(2)

    new_section, changed = replacer_fn(section)
    if not changed:
        return full_body, False

    new_full = full_body[:m.start()] + header + new_section + full_body[m.end():]
    return new_full, True


def extract_agenda_blocks(comment: str):
    
    blocks = {}
    text = comment or ""

    for agenda in AGENDA_TYPES:
        
        pattern = rf"\[{re.escape(agenda)}\]\s*([\s\S]*?)(?=\n\s*\[|\Z)"
        m = re.search(pattern, text)
        if m:
            blocks[agenda] = clean_text(m.group(1))

    return blocks


def update_agenda_from_blocks(full_body: str, comment: str, author: str):
    
    agenda_blocks = extract_agenda_blocks(comment)
    if not agenda_blocks:
        return full_body, False

    respondent = extract_mentions(comment)

    def replacer(section: str):
        lines = section.splitlines()
        changed = False

        for i, line in enumerate(lines):
            if not line.strip().startswith("|"):
                continue

            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            
            if len(cols) < 7:
                continue

            no, agenda, proposer, responder, answer, feedback, result_ = cols[:7]

            if proposer == author and agenda in agenda_blocks:
                new_answer = agenda_blocks[agenda]
                new_responder = respondent if respondent != "-" else author

                
                lines[i] = (
                    f"| {no} | {agenda} | {proposer} | {new_responder} | "
                    f"{new_answer} | {feedback} | {result_} |"
                )
                changed = True

        return ("\n".join(lines) + "\n"), changed

    return replace_in_section(full_body, SECTION_1_TITLE, replacer)


def update_willdo(full_body: str, author: str, what: str, goal: str, due: str):
    what = clean_text(what)
    goal = clean_text(goal)
    due = clean_text(due)

    def replacer(section: str):
        lines = section.splitlines()
        changed = False

        # 1) 작성자 행 중 placeholder 교체
        target_idx = None
        for i, line in enumerate(lines):
            if not line.strip().startswith("|"):
                continue

            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) < 4:
                continue

            c_what, c_who, c_goal, c_due = cols[:4]

            if c_who == author and "[업무 내용 입력]" in c_what:
                target_idx = i
                break

        new_row = f"| {what} | {author} | {goal} | {due} |"

        if target_idx is not None:
            lines[target_idx] = new_row
            changed = True
        else:
            
            last_table_line_idx = None
            for i, line in enumerate(lines):
                if line.strip().startswith("|"):
                    last_table_line_idx = i
            if last_table_line_idx is not None:
                lines.insert(last_table_line_idx + 1, new_row)
                changed = True

        return ("\n".join(lines) + "\n"), changed

    return replace_in_section(full_body, SECTION_2_TITLE, replacer)



def update_tbd(full_body: str, content: str, note: str, kind: str, dm: str, discuss: str):
    content = clean_text(content)
    note = clean_text(note)
    kind = clean_text(kind)
    dm = clean_text(dm)
    discuss = clean_text(discuss)

    def replacer(section: str):
        lines = section.splitlines()
        changed = False

        target_idx = None
        for i, line in enumerate(lines):
            if not line.strip().startswith("|"):
                continue

            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) < 5:
                continue

            c_content, c_note, c_kind, c_dm, c_discuss = cols[:5]
            if "[논의할 내용]" in c_content:
                target_idx = i
                break

        new_row = f"| {content} | {note} | {kind} | {dm} | {discuss} |"

        if target_idx is not None:
            lines[target_idx] = new_row
            changed = True
        else:
            last_table_line_idx = None
            for i, line in enumerate(lines):
                if line.strip().startswith("|"):
                    last_table_line_idx = i
            if last_table_line_idx is not None:
                lines.insert(last_table_line_idx + 1, new_row)
                changed = True

        return ("\n".join(lines) + "\n"), changed

    return replace_in_section(full_body, SECTION_3_TITLE, replacer)


new_body = body
changed_any = False


new_body, changed = update_agenda_from_blocks(new_body, comment_body, author_name)
changed_any = changed_any or changed


cmd = parse_command(comment_body)

if cmd[0] == "willdo":
    _, what, goal, due = cmd
    new_body, changed = update_willdo(new_body, author_name, what, goal, due)
    changed_any = changed_any or changed

elif cmd[0] == "tbd":
    _, content, note, kind, dm, discuss = cmd
    new_body, changed = update_tbd(new_body, content, note, kind, dm, discuss)
    changed_any = changed_any or changed

else:
    
    pass


if changed_any and new_body != body:
    issue.edit(body=new_body)
    print(f" Issue updated by {author_name}")
else:
    print("No update made.")

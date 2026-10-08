"""Optional: fills the app with ONE SAMPLE WEEK (focus sessions, hours, diary pages, an About me text),
so a screenshot or demo video is not empty and the AI has context to talk about.

    python seed_sample_week.py          # refuses to run if you already have data
    python seed_sample_week.py --force  # adds it anyway

It is sample data, not a real history: say so if you show it. Edit the texts below to make them yours."""
import sys, time
from backend import main as M

ABOUT = ("I am a civil engineering student finishing my degree. I am writing my thesis and learning Python and data analysis. "
         "My goal this year is to finish the thesis and find an internship abroad. My dream is a house with a garden and big windows. "
         "Writing a diary helps me see my progress; the hard part is staying consistent when I am tired.")
# (days ago, task, hours, diary page)
WEEK = [
    (7, "Thesis chapter 2", 3.5, "Started the week well. I finished the outline of chapter 2 and felt clear about what to do next."),
    (6, "Python exercises", 2.5, "Short day. I practised Python for a couple of hours, then went for a walk. A bit tired but happy I kept the habit."),
    (5, "Thesis chapter 2", 4.0, "Long focused session at the library. Chapter 2 is almost done. I am proud that I did not check my phone."),
    (4, "Internship applications", 3.0, "Spent the day on applications and my CV. It is stressful to wait for answers, but sending them felt good."),
    (3, "Structural analysis revision", 2.0, "Slept badly, so I only did two hours of revision. I decided to rest in the evening instead of forcing it."),
    (2, "Thesis chapter 3", 5.0, "Best day of the week. The proof finally made sense and I wrote four pages. I felt calm and motivated."),
    (1, "Thesis chapter 3", 3.5, "Kept the rhythm. Wrote the introduction of chapter 3 and planned the week ahead. Excited about the presentation."),
]

with M.conn() as con:
    busy = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] or con.execute("SELECT COUNT(*) FROM diary_pages").fetchone()[0]
    if busy and "--force" not in sys.argv:
        sys.exit("You already have sessions or diary pages. Nothing changed. Use --force to add the sample week anyway.")
    now, total = time.time(), 0.0
    for ago, task, hours, page in WEEK:
        day = time.strftime("%Y-%m-%d", time.localtime(now - ago * 86400))
        end = time.mktime(time.strptime(day + " 18:00", "%Y-%m-%d %H:%M"))      # the session ends at 18:00 that day
        con.execute("INSERT INTO sessions (kind, task, started, ended, hours) VALUES ('work', ?, ?, ?, ?)", (task, end - hours * 3600, end, hours))
        con.execute("INSERT OR REPLACE INTO diary_pages (day, text, ts) VALUES (?,?,?)", (day, page, end))
        total += hours
    M.earn(con, total)
    if not (con.execute("SELECT text FROM about WHERE id=1").fetchone()[0] or "").strip():
        con.execute("UPDATE about SET text=? WHERE id=1", (ABOUT,))
print(f"Sample week added: {total} hours and {len(WEEK)} diary pages. Restart the server (or refresh the page).")

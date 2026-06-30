"""Text Blast — standalone macOS app for sending personalized texts via iMessage."""

import argparse
import datetime as dt
import os
import sys

# macOS prints a scary "Tk is deprecated" warning for older Tcl/Tk — harmless with python.org Python
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext
except ImportError:
    print(
        "\nText Blast requires Python with Tkinter (the UI).\n\n"
        "On Mac, install Python from https://www.python.org/downloads/\n"
        "Then run:  ./run.sh\n",
        file=sys.stderr,
    )
    sys.exit(1)

import threading

from text_blast_lib import (
    _kc_get,
    _kc_set,
    apply_template,
    fetch_contractor_contacts,
    fetch_event_names,
    fetch_pod_names,
    fetch_staff_contacts,
    get_enriched,
    get_token,
    log_send_errors,
    normalize_phone,
    notify,
    parse_contacts,
    read_prefill,
    read_state,
    send_text_message,
    write_state,
)

APP_VERSION = "1.0.0"

BG = "#f8f9fd"
INPUT = "#f2f4f9"
TEXT = "#0f1117"
SUBTEXT = "#52596b"
MUTED = "#98a0b4"
SUCCESS = "#16a34a"
BORDER = "#e8ebf4"
LBLUE = "#90D5FF"
ACCENT = "#38bdb6"
ACCENT_HOV = "#2da39d"
BTN2 = "#e2e8f0"
BTN2_HV = "#cbd5e1"

FONT = ("SF Pro Display", 12)
FONT_SM = ("SF Pro Display", 11)
FONT_BOLD = ("SF Pro Display", 12, "bold")
FONT_TITLE = ("SF Pro Display", 18, "bold")
FONT_MONO = ("SF Mono", 11)


def sf(parent, **kw):
    kw.setdefault("bg", BG)
    kw.setdefault("bd", 0)
    kw.setdefault("highlightthickness", 0)
    return tk.Frame(parent, **kw)


def lbl(parent, text, font=FONT, color=TEXT, **kw):
    bg = kw.pop("bg", None)
    if bg is None:
        try:
            bg = parent.cget("bg")
        except Exception:
            bg = BG
    return tk.Label(parent, text=text, font=font, fg=color, bg=bg, **kw)


class PillButton(tk.Canvas):
    def __init__(self, parent, text, command, bg=ACCENT, fg="#ffffff",
                 hover=ACCENT_HOV, font=FONT_BOLD, padx=20, pady=8):
        tmp = tk.Label(parent, text=text, font=font)
        tmp.update_idletasks()
        tw, th = tmp.winfo_reqwidth(), tmp.winfo_reqheight()
        tmp.destroy()
        w, h = tw + padx * 2, th + pady * 2
        try:
            pbg = parent.cget("bg")
        except Exception:
            pbg = BG
        super().__init__(parent, width=w, height=h, bg=pbg,
                         bd=0, highlightthickness=0, cursor="hand2")
        self._bg, self._hover, self._fg = bg, hover, fg
        self._command = command
        r = h // 2
        self._shapes = [
            self.create_oval(0, 0, h, h, fill=bg, outline=bg),
            self.create_oval(w - h, 0, w, h, fill=bg, outline=bg),
            self.create_rectangle(r, 0, w - r, h, fill=bg, outline=bg),
        ]
        self._txt = self.create_text(w // 2, h // 2, text=text, font=font, fill=fg)
        self.bind("<Enter>", lambda e: self._recolor(self._hover))
        self.bind("<Leave>", lambda e: self._recolor(self._bg))
        self.bind("<Button-1>", self._on_click)

    def _recolor(self, color):
        try:
            for s in self._shapes:
                self.itemconfig(s, fill=color, outline=color)
        except tk.TclError:
            pass

    def _on_click(self, e):
        if getattr(self, "_disabled", False):
            return
        try:
            self._command()
        except Exception:
            pass


def rbtn(parent, text, command, **kw):
    kw.setdefault("bg", ACCENT)
    kw.setdefault("hover", ACCENT_HOV)
    kw.setdefault("fg", "#ffffff")
    kw.setdefault("font", FONT_BOLD)
    return PillButton(parent, text, command, **kw)


def dbtn(parent, text, command, **kw):
    kw.setdefault("bg", BTN2)
    kw.setdefault("hover", BTN2_HV)
    kw.setdefault("fg", TEXT)
    kw.setdefault("font", FONT)
    kw.setdefault("padx", 16)
    return PillButton(parent, text, command, **kw)


def bordered_text(parent, height=8, state="normal"):
    outer = tk.Frame(parent, bg=BORDER, bd=0, highlightthickness=0)
    text = tk.Text(outer, height=height, bg=INPUT, fg=TEXT, font=FONT_MONO,
                   relief="flat", bd=8, insertbackground=TEXT,
                   selectbackground=LBLUE, selectforeground="#000000",
                   wrap="word", state=state)
    text.pack(fill="both", expand=True, padx=1, pady=1)
    outer._text = text
    return outer


class TextBlastApp(tk.Tk):
    def __init__(self, event_name=None, prefill_path=None):
        super().__init__()
        self.title("Text Blast")
        self.geometry("920x820")
        self.minsize(820, 680)
        self.configure(bg=BG)

        self._enriched_contacts = []
        self._startup_event = event_name
        self._startup_prefill = prefill_path
        self._pod_vars = {}
        self._pending_pod_selection = []
        self._save_timer = None
        self._restoring_state = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._startup_load)

    def _build_ui(self):
        root = sf(self)
        root.pack(fill="both", expand=True, padx=20, pady=16)

        lbl(root, "Text Blast", font=FONT_TITLE).pack(anchor="w")
        lbl(root, "Send personalized texts to coaches/staff via iMessage from your phone number.",
            color=MUTED, font=FONT_SM).pack(anchor="w", pady=(2, 8))

        # Settings strip
        settings = sf(root)
        settings.pack(fill="x", pady=(0, 10))
        lbl(settings, "Airtable Token:", font=FONT_SM, color=SUBTEXT).pack(side="left")
        self._token_var = tk.StringVar(value=get_token())
        self._token_entry = tk.Entry(settings, textvariable=self._token_var, font=FONT_SM,
                 bg=INPUT, fg=TEXT, relief="flat", bd=6,
                 insertbackground=TEXT, width=40, show="•")
        self._token_entry.pack(side="left", padx=6)
        self._token_entry.bind("<FocusOut>", lambda e: self._save_token(quiet=True))
        self._token_var.trace_add("write", lambda *_: self._schedule_save())
        dbtn(settings, "Save", self._save_token, padx=10, pady=4).pack(side="left")
        self._token_status = lbl(settings, "", color=MUTED, font=FONT_SM)
        self._token_status.pack(side="left", padx=8)

        top = sf(root)
        top.pack(fill="both", expand=True)

        # Contacts (left)
        left = sf(top)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        lbl(left, "Contacts", font=FONT_BOLD).pack(anchor="w")

        # Source selector
        src_row = sf(left)
        src_row.pack(fill="x", pady=(4, 2))
        lbl(src_row, "Source:", font=FONT_SM, color=SUBTEXT).pack(side="left")
        self._source_var = tk.StringVar(value="staffing")
        for val, label in [("staffing", "Event Staffing"), ("contractors", "Contractors by Pod")]:
            tk.Radiobutton(
                src_row, text=label, variable=self._source_var, value=val,
                font=FONT_SM, bg=BG, fg=TEXT, activebackground=BG,
                selectcolor=INPUT, command=self._on_source_change,
            ).pack(side="left", padx=(8, 0))

        self._filters_frame = sf(left)
        self._filters_frame.pack(fill="x", pady=(2, 0))

        # Event staffing filters
        self._staffing_frame = sf(self._filters_frame)
        self._staffing_frame.pack(fill="x")

        ev_row = sf(self._staffing_frame)
        ev_row.pack(fill="x", pady=(2, 2))
        lbl(ev_row, "Event:", font=FONT_SM, color=SUBTEXT).pack(side="left")
        self._event_var = tk.StringVar(value="All Events")
        self._event_menu = tk.OptionMenu(ev_row, self._event_var, "All Events")
        self._event_menu.configure(font=FONT_SM, bg=INPUT, fg=TEXT,
                                   highlightthickness=0, relief="flat",
                                   activebackground=BORDER, width=35)
        self._event_menu["menu"].configure(bg=INPUT, fg=TEXT, font=FONT_SM)
        self._event_menu.pack(side="left", padx=6)
        dbtn(ev_row, "🔄", self._refresh_events, padx=8, pady=4).pack(side="left")
        self._event_refresh_status = lbl(ev_row, "", color=MUTED, font=FONT_SM)
        self._event_refresh_status.pack(side="left", padx=6)

        # Contractor filters
        self._contractor_frame = sf(self._filters_frame)

        pod_hdr = sf(self._contractor_frame)
        pod_hdr.pack(fill="x", pady=(2, 2))
        lbl(pod_hdr, "Pods:", font=FONT_SM, color=SUBTEXT).pack(side="left")
        dbtn(pod_hdr, "🔄 Refresh", self._refresh_pods, padx=8, pady=3).pack(side="left", padx=4)
        dbtn(pod_hdr, "All", self._select_all_pods, padx=8, pady=3).pack(side="left", padx=2)
        dbtn(pod_hdr, "Clear", self._clear_pods, padx=8, pady=3).pack(side="left", padx=2)
        self._pod_count_label = lbl(pod_hdr, "", color=MUTED, font=FONT_SM)
        self._pod_count_label.pack(side="left", padx=8)

        pod_scroll_outer = tk.Frame(self._contractor_frame, bg=BORDER, height=120)
        pod_scroll_outer.pack(fill="x", pady=(2, 4))
        pod_scroll_outer.pack_propagate(False)
        self._pod_canvas = tk.Canvas(pod_scroll_outer, bg=INPUT, highlightthickness=0, height=118)
        pod_scroll = tk.Scrollbar(pod_scroll_outer, orient="vertical", command=self._pod_canvas.yview)
        self._pod_canvas.configure(yscrollcommand=pod_scroll.set)
        pod_scroll.pack(side="right", fill="y")
        self._pod_canvas.pack(side="left", fill="both", expand=True)
        self._pod_inner = sf(self._pod_canvas, bg=INPUT)
        self._pod_canvas_window = self._pod_canvas.create_window((0, 0), window=self._pod_inner, anchor="nw")
        self._pod_inner.bind("<Configure>", lambda e: self._pod_canvas.configure(
            scrollregion=self._pod_canvas.bbox("all")))

        worked_row = sf(self._contractor_frame)
        worked_row.pack(fill="x", pady=(0, 4))
        lbl(worked_row, "Event work:", font=FONT_SM, color=SUBTEXT).pack(side="left")
        self._worked_var = tk.StringVar(value="Any")
        self._worked_menu = tk.OptionMenu(
            worked_row, self._worked_var,
            "Any", "Worked this year", "Not worked this year",
        )
        self._worked_menu.configure(font=FONT_SM, bg=INPUT, fg=TEXT,
                                    highlightthickness=0, relief="flat", width=18)
        self._worked_menu["menu"].configure(bg=INPUT, fg=TEXT, font=FONT_SM)
        self._worked_menu.pack(side="left", padx=6)
        lbl(worked_row, "any / worked this year / not this year",
            color=MUTED, font=FONT_SM).pack(side="left")

        self._on_source_change()

        pull_row = sf(left)
        pull_row.pack(fill="x", pady=(2, 6))
        rbtn(pull_row, "📥  Pull from Airtable", self._pull_contacts,
             padx=14, pady=5).pack(side="left")
        self._pull_status = lbl(pull_row, "Or paste manually", color=MUTED, font=FONT_SM)
        self._pull_status.pack(side="left", padx=10)

        contacts_outer = bordered_text(left, height=10)
        contacts_outer.pack(fill="both", expand=True)
        self._contacts_text = contacts_outer._text

        # Template (right)
        right = sf(top)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))
        lbl(right, "Message Template", font=FONT_BOLD).pack(anchor="w")
        lbl(right, "Variables: {name} (first name)  {site}  {computer}  {channel}  {date}  {pod}  {region}",
            color=MUTED, font=FONT_SM).pack(anchor="w", pady=(2, 6))

        tmpl_outer = bordered_text(right, height=5)
        tmpl_outer.pack(fill="x")
        self._template_text = tmpl_outer._text
        self._template_text.insert("1.0",
            "Hi {name}, this is a reminder from GOLS. You're assigned to "
            "{site} on {date} with {computer}. "
            "Arrive 15 minutes early. See you there!")

        cc_row = sf(right)
        cc_row.pack(fill="x", pady=(8, 0))
        lbl(cc_row, "CC every text to:", font=FONT_SM, color=SUBTEXT).pack(side="left")
        self._cc_var = tk.StringVar()
        tk.Entry(cc_row, textvariable=self._cc_var, font=FONT_SM,
                 bg=INPUT, fg=TEXT, relief="flat", bd=6,
                 insertbackground=TEXT, width=18).pack(side="left", padx=6)
        lbl(cc_row, "(group if possible; otherwise separate copy to CC)", color=MUTED, font=FONT_SM).pack(side="left")

        lbl(right, "Preview (first contact)", font=FONT_BOLD).pack(anchor="w", pady=(12, 0))
        preview_outer = bordered_text(right, height=4, state="disabled")
        preview_outer.pack(fill="x", pady=(4, 0))
        self._preview_text = preview_outer._text

        act = sf(root)
        act.pack(fill="x", pady=(12, 0))
        dbtn(act, "🔄  Preview", self._preview).pack(side="left", padx=(0, 8))
        self._send_btn = rbtn(act, "📱  Send All", self._send_all)
        self._send_btn.pack(side="left", padx=(0, 8))
        self._status = lbl(act, "", color=MUTED, font=FONT_SM)
        self._status.pack(side="left", padx=12)

        if sys.platform != "darwin":
            self._status.configure(
                text="Text Blast requires macOS — preview works, sending disabled",
                fg=ACCENT)

        self._progress = lbl(root, "", color=MUTED, font=FONT_SM)
        self._progress.pack(anchor="w", pady=(8, 0))

        self._contacts_text.bind("<KeyRelease>", lambda e: self._schedule_save())
        self._template_text.bind("<KeyRelease>", lambda e: self._schedule_save())
        self._cc_var.trace_add("write", lambda *_: self._schedule_save())
        self._source_var.trace_add("write", lambda *_: self._schedule_save())
        self._event_var.trace_add("write", lambda *_: self._schedule_save())
        self._worked_var.trace_add("write", lambda *_: self._schedule_save())

        if get_token():
            self._token_status.configure(text="✓ Saved", fg=SUCCESS)

    def _on_source_change(self):
        if self._source_var.get() == "contractors":
            self._staffing_frame.pack_forget()
            self._contractor_frame.pack(fill="x")
        else:
            self._contractor_frame.pack_forget()
            self._staffing_frame.pack(fill="x")

    def _update_pod_count(self):
        selected = sum(1 for v in self._pod_vars.values() if v.get())
        total = len(self._pod_vars)
        if total:
            label = f"{selected}/{total} pods selected" if selected else f"0/{total} (all pods if none selected)"
        else:
            label = "Refresh pods to load list"
        self._pod_count_label.configure(text=label)
        self._schedule_save()

    def _select_all_pods(self):
        for v in self._pod_vars.values():
            v.set(True)
        self._update_pod_count()

    def _clear_pods(self):
        for v in self._pod_vars.values():
            v.set(False)
        self._update_pod_count()

    def _refresh_pods(self):
        self._pod_count_label.configure(text="Loading...", fg=MUTED)
        self.update_idletasks()

        def task():
            pods = fetch_pod_names()
            def done():
                for w in self._pod_inner.winfo_children():
                    w.destroy()
                self._pod_vars = {}
                for i, pod in enumerate(pods):
                    var = tk.BooleanVar(value=False)
                    self._pod_vars[pod] = var
                    row = i // 2
                    col = i % 2
                    tk.Checkbutton(
                        self._pod_inner, text=pod, variable=var, font=FONT_SM,
                        bg=INPUT, fg=TEXT, activebackground=INPUT,
                        selectcolor=INPUT, command=self._update_pod_count,
                    ).grid(row=row, column=col, sticky="w", padx=8, pady=2)
                self._update_pod_count()
                self._apply_pending_pods()
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _schedule_save(self):
        if self._restoring_state:
            return
        if self._save_timer:
            self.after_cancel(self._save_timer)
        self._save_timer = self.after(1500, self._save_state)

    def _collect_state(self):
        return {
            "source": self._source_var.get(),
            "event": self._event_var.get(),
            "worked_filter": self._worked_var.get(),
            "selected_pods": [p for p, v in self._pod_vars.items() if v.get()],
            "contacts_text": self._contacts_text.get("1.0", "end").strip(),
            "template": self._template_text.get("1.0", "end").strip(),
            "cc": self._cc_var.get().strip(),
            "enriched_contacts": self._enriched_contacts,
        }

    def _apply_state(self, data):
        if not data:
            return
        self._restoring_state = True
        try:
            source = data.get("source")
            if source in ("staffing", "contractors"):
                self._source_var.set(source)
                self._on_source_change()

            event = data.get("event")
            if event:
                self._event_var.set(event)

            worked = data.get("worked_filter")
            if worked:
                self._worked_var.set(worked)

            self._pending_pod_selection = data.get("selected_pods") or []

            contacts_text = data.get("contacts_text", "")
            if contacts_text:
                self._contacts_text.delete("1.0", "end")
                self._contacts_text.insert("1.0", contacts_text)

            template = data.get("template", "")
            if template:
                self._template_text.delete("1.0", "end")
                self._template_text.insert("1.0", template)

            cc = data.get("cc", "")
            if cc:
                self._cc_var.set(cc)

            self._enriched_contacts = data.get("enriched_contacts") or []
            if self._enriched_contacts:
                self._pull_status.configure(
                    text=f"✓ {len(self._enriched_contacts)} contacts restored", fg=SUCCESS)
        finally:
            self._restoring_state = False

    def _save_state(self):
        self._save_timer = None
        if self._restoring_state:
            return
        try:
            write_state(self._collect_state())
        except Exception:
            pass

    def _save_token(self, quiet=False):
        v = self._token_var.get().strip()
        if not v:
            if not quiet:
                messagebox.showwarning("Empty", "Paste your Airtable token first.")
            return
        _kc_set("airtable_token", "AIRTABLE_TOKEN", v)
        self._token_status.configure(text="✓ Saved", fg=SUCCESS)

    def _on_close(self):
        self._save_token(quiet=True)
        self._save_state()
        self.destroy()

    def _apply_pending_pods(self):
        if not self._pending_pod_selection:
            return
        for pod in self._pending_pod_selection:
            if pod in self._pod_vars:
                self._pod_vars[pod].set(True)
        self._update_pod_count()
        self._pending_pod_selection = []

    def _startup_load(self):
        if self._startup_prefill and os.path.exists(self._startup_prefill):
            try:
                data = read_prefill(self._startup_prefill)
                self._contacts_text.delete("1.0", "end")
                self._contacts_text.insert("1.0", data.get("contacts_text", ""))
                self._template_text.delete("1.0", "end")
                self._template_text.insert("1.0", data.get("template", ""))
                self._enriched_contacts = data.get("enriched_contacts", [])
                self._pull_status.configure(
                    text=f"✓ {len(self._enriched_contacts)} contacts loaded", fg=SUCCESS)
            except Exception as e:
                self._pull_status.configure(text=f"Prefill error: {e}", fg=ACCENT)
        else:
            saved = read_state()
            if saved:
                self._apply_state(saved)
            if self._startup_event:
                self._event_var.set(self._startup_event)
                self._pull_contacts()

        if self._source_var.get() == "contractors":
            self._refresh_pods()

    def _refresh_events(self):
        self._event_refresh_status.configure(text="⏳", fg=MUTED)
        self.update_idletasks()

        def task():
            events = fetch_event_names()
            def done():
                menu = self._event_menu["menu"]
                menu.delete(0, "end")
                menu.add_command(label="All Events",
                                 command=lambda: self._event_var.set("All Events"))
                for ev in events:
                    display = ev[:55] + "..." if len(ev) > 55 else ev
                    menu.add_command(label=display,
                                     command=lambda e=ev: self._event_var.set(e))
                self._event_refresh_status.configure(
                    text=f"✓ {len(events)} events", fg=SUCCESS)
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _pull_contacts(self):
        self._save_token(quiet=True)
        self._pull_status.configure(text="⏳ Fetching from Airtable...", fg=MUTED)
        self.update_idletasks()
        source = self._source_var.get()

        def task():
            if source == "contractors":
                selected_pods = [p for p, v in self._pod_vars.items() if v.get()]
                worked_map = {
                    "Any": "any",
                    "Worked this year": "yes",
                    "Not worked this year": "no",
                }
                worked = worked_map.get(self._worked_var.get(), "any")
                contacts = fetch_contractor_contacts(
                    pods=selected_pods or None,
                    worked_filter=worked,
                )
            else:
                selected = self._event_var.get()
                min_d, max_d, event_name = None, None, None
                if selected and selected != "All Events":
                    event_name = selected
                else:
                    event_dates = _kc_get("event_dates", "EVENT_DATES")
                    if event_dates and " - " in event_dates:
                        try:
                            parts = event_dates.split(" - ")
                            d1 = dt.datetime.strptime(parts[0].strip(), "%m/%d/%Y").date()
                            d2 = dt.datetime.strptime(parts[1].strip(), "%m/%d/%Y").date()
                            min_d, max_d = str(d1), str(d2)
                        except Exception:
                            pass
                contacts = fetch_staff_contacts(min_d, max_d, event_name)

            def done():
                if not contacts:
                    self._pull_status.configure(
                        text="No contacts found — adjust filters or check Airtable",
                        fg=ACCENT)
                    return
                self._enriched_contacts = contacts
                self._contacts_text.delete("1.0", "end")
                lines = [f"{c['name']}\t\t{c['phone']}" for c in contacts]
                self._contacts_text.insert("1.0", "\n".join(lines))
                self._pull_status.configure(
                    text=f"✓ {len(contacts)} contacts pulled", fg=SUCCESS)
                self._save_state()

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _preview(self):
        contacts = parse_contacts(self._contacts_text.get("1.0", "end").strip())
        if not contacts:
            self._status.configure(text="No contacts found — check format", fg=ACCENT)
            return
        template = self._template_text.get("1.0", "end").strip()
        name, phone = contacts[0]
        enriched = get_enriched(name, phone, self._enriched_contacts)
        preview = apply_template(template, enriched)
        self._preview_text.configure(state="normal")
        self._preview_text.delete("1.0", "end")
        self._preview_text.insert("1.0", f"To: {enriched['name']} ({phone})\n\n{preview}")
        self._preview_text.configure(state="disabled")
        raw_lines = [l.strip() for l in self._contacts_text.get("1.0", "end").splitlines()
                     if l.strip() and not l.strip().startswith("---")]
        dupes = len(raw_lines) - len(contacts)
        status = f"✓ {len(contacts)} unique contact(s) ready"
        if dupes > 0:
            status += f" ({dupes} duplicates removed)"
        self._status.configure(text=status, fg=SUCCESS)

    def _send_all(self):
        if sys.platform != "darwin":
            messagebox.showinfo("macOS Only",
                "Text Blast uses iMessage which requires macOS.\n"
                "Run this from a Mac to send texts.")
            return
        contacts = parse_contacts(self._contacts_text.get("1.0", "end").strip())
        if not contacts:
            self._status.configure(text="No contacts found", fg=ACCENT)
            return
        template = self._template_text.get("1.0", "end").strip()
        if not template:
            self._status.configure(text="Write a message first", fg=ACCENT)
            return
        count = len(contacts)
        first_msg = apply_template(
            template, get_enriched(contacts[0][0], contacts[0][1], self._enriched_contacts))
        if not messagebox.askyesno("Send Texts",
                f"Send {count} individual text(s) from your phone number?\n\n"
                f"First message preview:\n"
                f"To: {contacts[0][1]}\n"
                f"{first_msg[:100]}..."):
            return
        self._send_btn._disabled = True
        self._status.configure(text=f"Sending 0/{count}...", fg=MUTED)

        cc_raw = self._cc_var.get().strip()
        cc_phone = normalize_phone(cc_raw) if cc_raw else None

        self._send_state = {
            "contacts": contacts,
            "template": template,
            "cc_phone": cc_phone,
            "index": 0,
            "sent": 0,
            "failed": 0,
            "errors": [],
            "copy_fallbacks": 0,
            "count": count,
            "sending": True,
        }
        self._send_next_message()

    def _send_next_message(self):
        state = getattr(self, "_send_state", None)
        if not state or not state.get("sending"):
            return

        idx = state["index"]
        if idx >= state["count"]:
            self._send_finish()
            return

        name, phone = state["contacts"][idx]
        enriched = get_enriched(name, phone, self._enriched_contacts)
        msg = apply_template(state["template"], enriched)

        def worker(n=name, p=phone, m=msg):
            try:
                ok, err = send_text_message(p, m, state["cc_phone"])
            except Exception as exc:
                ok, err = False, str(exc)
            self.after(0, lambda: self._send_message_done(ok, err, n, p))

        threading.Thread(target=worker, daemon=True).start()

    def _send_message_done(self, ok, err, name, phone):
        state = getattr(self, "_send_state", None)
        if not state or not state.get("sending"):
            return

        if ok:
            state["sent"] += 1
            if err == "separate_copy":
                state["copy_fallbacks"] = state.get("copy_fallbacks", 0) + 1
        else:
            state["failed"] += 1
            state["errors"].append({
                "name": name or "(no name)",
                "phone": phone,
                "error": err or "Unknown error",
            })

        state["index"] += 1
        sent, failed, total = state["sent"], state["failed"], state["count"]
        self._progress.configure(
            text=f"Sent {sent}/{total}" + (f" ({failed} failed)" if failed else ""))
        self._status.configure(text=f"Sending {sent + failed}/{total}...", fg=MUTED)

        if state["index"] < state["count"]:
            delay = 5000 if state.get("cc_phone") else 2000
            self.after(delay, self._send_next_message)
        else:
            self.after(100, self._send_finish)

    def _send_finish(self):
        state = getattr(self, "_send_state", None)
        if not state:
            return
        state["sending"] = False
        self._send_btn._disabled = False
        sent, failed = state["sent"], state["failed"]
        errors = state.get("errors", [])

        status = f"✓ Done — {sent} sent"
        if failed:
            status += f", {failed} failed"
        copy_fb = state.get("copy_fallbacks", 0)
        if copy_fb:
            status += f" ({copy_fb} as separate CC copy — enable Accessibility for group texts)"
        self._status.configure(text=status, fg=SUCCESS if not failed else ACCENT)
        self._progress.configure(text="")

        self.lift()
        self.focus_force()

        if sent and not failed:
            notify("Text Blast Complete", f"{sent} messages sent")
        elif failed:
            notify("Text Blast Complete", f"{sent} sent, {failed} failed")
            log_path = log_send_errors(errors)
            self._show_send_error_log(sent, failed, errors, log_path)
        else:
            messagebox.showwarning(
                "Nothing sent",
                "No messages were sent. Check Messages and automation permissions.",
                parent=self)
        self._save_state()

    def _show_send_error_log(self, sent, failed, errors, log_path):
        """Pop up a scrollable error log for failed sends."""
        win = tk.Toplevel(self)
        win.title("Text Blast — Send Error Log")
        win.geometry("640x420")
        win.minsize(480, 300)
        win.configure(bg=BG)
        win.transient(self)

        summary = (
            f"{failed} of {sent + failed} message(s) failed"
            + (f" ({sent} sent)" if sent else "")
        )
        lbl(win, summary, font=FONT_BOLD, color=ACCENT).pack(anchor="w", padx=16, pady=(14, 4))
        lbl(win,
            "Group texts need Automation (Messages) and Accessibility (Python/Terminal) in System Settings",
            font=FONT_SM, color=MUTED).pack(anchor="w", padx=16, pady=(0, 8))

        text = scrolledtext.ScrolledText(
            win, font=FONT_MONO, bg=INPUT, fg=TEXT, wrap="word",
            relief="flat", bd=8, insertbackground=TEXT)
        text.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        lines = []
        for i, e in enumerate(errors, 1):
            lines.append(f"{i}. {e['name']}  ({e['phone']})")
            lines.append(f"   {e['error']}")
            lines.append("")
        if log_path:
            lines.append(f"Log saved to: {log_path}")
        text.insert("1.0", "\n".join(lines).strip())
        text.configure(state="disabled")

        btn_row = sf(win)
        btn_row.pack(fill="x", padx=16, pady=(0, 14))
        dbtn(btn_row, "Close", win.destroy, padx=14, pady=6).pack(side="right")
        if log_path:
            def open_log():
                os.system(f'open -R "{log_path}"')
            dbtn(btn_row, "Show Log File", open_log, padx=14, pady=6).pack(side="right", padx=(0, 8))

        win.lift()
        win.focus_force()


def main():
    if sys.platform == "darwin":
        import multiprocessing
        multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Text Blast — send personalized texts via iMessage")
    parser.add_argument("--event", help="Pre-select event and pull contacts on launch")
    parser.add_argument("--prefill", help="Path to prefill JSON (default: ~/.sitetools/text_blast_prefill.json)")
    args = parser.parse_args()
    prefill = args.prefill
    app = TextBlastApp(event_name=args.event, prefill_path=prefill)
    app.mainloop()


if __name__ == "__main__":
    main()

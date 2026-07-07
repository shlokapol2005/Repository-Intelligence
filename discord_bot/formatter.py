"""
formatter.py — Converts raw FastAPI JSON responses into Discord Embeds.

Discord embed limits:
  - description: 4096 chars max
  - field value:  1024 chars max
  - max 25 fields per embed
"""
import discord

# Colour palette for the bot
COLOUR_DEFAULT  = 0x5865F2   # Discord blurple
COLOUR_SUCCESS  = 0x57F287   # Green
COLOUR_WARNING  = 0xFEE75C   # Yellow
COLOUR_DANGER   = 0xED4245   # Red
COLOUR_INFO     = 0x5DADE2   # Blue

RISK_COLOURS = {
    "Low":      COLOUR_SUCCESS,
    "Medium":   COLOUR_WARNING,
    "High":     0xE67E22,    # Orange
    "Critical": COLOUR_DANGER,
}

_DISCORD_LIMIT = 4000   # leave a small buffer under the 4096 cap


def _trim(text: str, limit: int = _DISCORD_LIMIT) -> str:
    """Hard-truncate a string and add an ellipsis if needed."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _field_trim(text: str) -> str:
    return _trim(text, 1020)


# ── Individual formatters ──────────────────────────────────────────────────────

def format_qa(result: dict, repo_name: str, question: str) -> discord.Embed:
    embed = discord.Embed(
        title="🔍 Answer",
        description=_trim(result.get("answer", "No answer returned.")),
        colour=COLOUR_DEFAULT,
    )
    embed.set_author(name=f"Repo: {repo_name}")
    embed.set_footer(text=f"Q: {question[:100]}")

    sources = result.get("sources", [])
    if sources:
        embed.add_field(
            name="📄 Files referenced",
            value=_field_trim("\n".join(f"`{s}`" for s in sources[:10])),
            inline=False,
        )

    if not result.get("confidence_ok", True):
        embed.add_field(
            name="⚠️ Low confidence",
            value="The vector search score was below threshold. The answer may be less accurate.",
            inline=False,
        )
    return embed


def format_flow(result: dict, repo_name: str, feature: str) -> discord.Embed:
    embed = discord.Embed(
        title="🔄 Feature Flow Trace",
        description=_trim(result.get("explanation", "No explanation returned.")),
        colour=COLOUR_INFO,
    )
    embed.set_author(name=f"Repo: {repo_name}")
    embed.set_footer(text=f"Feature: {feature[:80]}")

    steps = result.get("steps_structured", [])
    for step in steps[:15]:            # cap at 15 steps to stay under 25-field limit
        step_num = step.get("step", "?")
        file_    = step.get("file", "?")
        fn       = step.get("function", "")
        action   = step.get("action", "")
        stype    = step.get("type", "")

        label = f"Step {step_num} — `{file_}`"
        value = ""
        if fn:     value += f"**Function:** `{fn}`\n"
        if stype:  value += f"**Type:** {stype}\n"
        if action: value += f"{action}"

        embed.add_field(name=label, value=_field_trim(value) or "—", inline=False)

    disclaimer = result.get("disclaimer", "")
    if disclaimer:
        embed.add_field(name="ℹ️ Note", value=_field_trim(disclaimer), inline=False)

    return embed


def format_impact(result: dict, repo_name: str, target_file: str) -> discord.Embed:
    impact_data = result.get("impact", {})
    risk = impact_data.get("risk", "Unknown")
    affected = impact_data.get("affected_files", [])
    count = impact_data.get("count", len(affected))

    colour = RISK_COLOURS.get(risk, COLOUR_DEFAULT)

    embed = discord.Embed(
        title=f"💥 Impact Analysis",
        description=_trim(result.get("risk_explanation", "No explanation available.")),
        colour=colour,
    )
    embed.set_author(name=f"Repo: {repo_name}")
    embed.add_field(name="🎯 Target file", value=f"`{target_file}`", inline=True)
    embed.add_field(name="⚠️ Risk level",  value=f"**{risk}**",      inline=True)
    embed.add_field(name="📊 Affected",    value=f"**{count}** files", inline=True)

    if affected:
        shown    = affected[:20]
        leftover = len(affected) - len(shown)
        lines    = "\n".join(f"`{f}`" for f in shown)
        if leftover > 0:
            lines += f"\n_...and {leftover} more_"
        embed.add_field(name="📁 Affected files", value=_field_trim(lines), inline=False)

    return embed


def format_architecture(result: dict, repo_name: str) -> list[discord.Embed]:
    """Returns a list of embeds (summary + mermaid code block, split if needed)."""
    summary = result.get("summary", "No summary available.")
    mermaid = result.get("mermaid", "")

    embeds = []

    # First embed: summary
    e1 = discord.Embed(
        title="🏗️ Architecture Overview",
        description=_trim(summary),
        colour=COLOUR_SUCCESS,
    )
    e1.set_author(name=f"Repo: {repo_name}")
    embeds.append(e1)

    # Second embed: Mermaid diagram as a code block
    if mermaid:
        # Discord doesn't render Mermaid natively, but the code block looks clean
        diagram_text = f"```\n{mermaid[:3800]}\n```"
        e2 = discord.Embed(
            title="📊 Dependency Diagram (Mermaid)",
            description=diagram_text,
            colour=COLOUR_DEFAULT,
        )
        e2.set_footer(text="Paste the code at mermaid.live to view interactively")
        embeds.append(e2)

    return embeds


def format_dead_code(result: dict, repo_name: str) -> discord.Embed:
    dead_files = result.get("dead_code", [])
    count      = len(dead_files)

    embed = discord.Embed(
        title="🪦 Dead Code Report",
        description=(
            f"Found **{count}** potentially unused file(s) in `{repo_name}`.\n"
            "These files have no other files importing them."
        ),
        colour=COLOUR_WARNING if count else COLOUR_SUCCESS,
    )
    embed.set_author(name=f"Repo: {repo_name}")

    if dead_files:
        shown    = dead_files[:25]
        leftover = count - len(shown)
        lines    = "\n".join(f"`{f}`" for f in shown)
        if leftover:
            lines += f"\n_...and {leftover} more_"
        embed.add_field(name="📁 Unused files", value=_field_trim(lines), inline=False)
    else:
        embed.add_field(name="✅ All clear", value="No dead code detected!", inline=False)

    return embed


def format_onboarding(result: dict, repo_name: str) -> list[discord.Embed]:
    """Returns one embed per learning module (max 5 embeds to avoid spam)."""
    path = result.get("learning_path", [])
    embeds = []

    intro = discord.Embed(
        title="📚 Onboarding Guide",
        description=f"Here's a suggested learning path for **{repo_name}**:",
        colour=COLOUR_SUCCESS,
    )
    embeds.append(intro)

    for module in path[:5]:
        m_title  = module.get("title", f"Module {module.get('module', '?')}")
        concepts = module.get("concepts", [])
        files    = module.get("key_files", [])
        exercise = module.get("exercise", "")
        time_est = module.get("estimated_time", "")

        desc = ""
        if time_est: desc += f"⏱️ **{time_est}**\n\n"
        if concepts: desc += "**Key concepts:**\n" + "\n".join(f"• {c}" for c in concepts[:5]) + "\n\n"
        if files:    desc += "**Key files:**\n"    + "\n".join(f"`{f}`" for f in files[:5])    + "\n\n"
        if exercise: desc += f"**Exercise:** {exercise}"

        e = discord.Embed(
            title=f"📖 {m_title}",
            description=_trim(desc),
            colour=COLOUR_DEFAULT,
        )
        embeds.append(e)

    return embeds


def format_loaded(repo_name: str, repo_path: str, scan_result: dict) -> discord.Embed:
    """Confirmation embed after a repo is loaded."""
    total_files = scan_result.get("total_files", "?")
    stats       = scan_result.get("graph_stats", {})
    nodes       = stats.get("total_nodes", "?")
    edges       = stats.get("total_edges", "?")

    embed = discord.Embed(
        title="✅ Repository Loaded",
        description=f"**{repo_name}** is ready. All commands in this channel will now use this repo.",
        colour=COLOUR_SUCCESS,
    )
    embed.add_field(name="📁 Files scanned", value=str(total_files), inline=True)
    embed.add_field(name="🔗 Graph nodes",   value=str(nodes),       inline=True)
    embed.add_field(name="↔️ Graph edges",   value=str(edges),       inline=True)
    embed.set_footer(text=f"Path: {repo_path}")
    return embed


def format_error(title: str, detail: str) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=_trim(detail),
        colour=COLOUR_DANGER,
    )


def format_no_repo() -> discord.Embed:
    return discord.Embed(
        title="⚠️ No Repository Loaded",
        description=(
            "This channel doesn't have a repository loaded yet.\n\n"
            "Use `/repobot load <github_url>` to clone and scan a repo first.\n"
            "Example: `/repobot load https://github.com/django/django`"
        ),
        colour=COLOUR_WARNING,
    )

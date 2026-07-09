"""
commands.py — All /repobot slash command handlers.

Every command follows the same pattern:
  1. interaction.response.defer()  ← shows Discord "thinking..." spinner immediately
  2. state.get_repo()              ← look up which repo this channel uses
  3. api_client.*()                ← call the FastAPI backend (async, non-blocking)
  4. formatter.*()                 ← turn JSON into a Discord Embed
  5. interaction.followup.send()   ← send the final reply
"""
import io

import discord
from discord import app_commands

import api_client
import formatter
import state


def register(tree: app_commands.CommandTree) -> None:
    """Register all /repobot sub-commands onto the command tree."""

    repobot = app_commands.Group(
        name="repobot",
        description="Code Detective — ask anything about your repository",
    )

    # ── /repobot load <github_url> ─────────────────────────────────────────────

    @repobot.command(name="load", description="Clone and scan a GitHub repo for this channel")
    @app_commands.describe(github_url="Full GitHub URL, e.g. https://github.com/django/django")
    async def cmd_load(interaction: discord.Interaction, github_url: str):
        await interaction.response.defer(thinking=True)
        try:
            # Step 1 — Clone
            clone_result = await api_client.clone_repo(github_url)
            repo_path    = clone_result["local_path"]
            repo_name    = clone_result.get("repo_name", github_url.split("/")[-1])

            # Step 2 — Scan + build index
            scan_result  = await api_client.scan_repo(repo_path)
            index_name   = scan_result.get("index_name", "")

            # Step 3 — Bind to channel (store the GitHub URL as the portable
            # identifier for deep links, so they work against any backend)
            state.set_repo(
                interaction.channel_id, repo_path, index_name, repo_name,
                github_url=github_url,
            )

            embed = formatter.format_loaded(repo_name, repo_path, scan_result)
            await interaction.followup.send(embed=embed)

        except Exception as exc:
            await interaction.followup.send(
                embed=formatter.format_error("Load failed", str(exc))
            )

    # ── /repobot qa <question> ─────────────────────────────────────────────────

    @repobot.command(name="qa", description="Ask a natural-language question about the loaded repo")
    @app_commands.describe(question="E.g. 'Where is JWT authentication handled?'")
    async def cmd_qa(interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)
        repo = state.get_repo(interaction.channel_id)
        if not repo:
            await interaction.followup.send(embed=formatter.format_no_repo())
            return
        try:
            result = await api_client.ask_question(
                repo["repo_path"], repo["index_name"], question
            )
            embed = formatter.format_qa(result, repo["repo_name"], question)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(
                embed=formatter.format_error("Q&A failed", str(exc))
            )

    # ── /repobot trace <feature> ───────────────────────────────────────────────

    @repobot.command(name="trace", description="Trace the code flow for a feature or user action")
    @app_commands.describe(feature="E.g. 'user login', 'payment processing', 'file upload'")
    async def cmd_trace(interaction: discord.Interaction, feature: str):
        await interaction.response.defer(thinking=True)
        repo = state.get_repo(interaction.channel_id)
        if not repo:
            await interaction.followup.send(embed=formatter.format_no_repo())
            return
        try:
            result = await api_client.trace_flow(
                repo["repo_path"], repo["index_name"], feature
            )
            embed = formatter.format_flow(result, repo["repo_name"], feature)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(
                embed=formatter.format_error("Flow trace failed", str(exc))
            )

    # ── /repobot impact <file> ─────────────────────────────────────────────────

    @repobot.command(name="impact", description="Show what breaks if a given file changes")
    @app_commands.describe(file="Relative file path, e.g. 'backend/utils/scanner.py'")
    async def cmd_impact(interaction: discord.Interaction, file: str):
        await interaction.response.defer(thinking=True)
        repo = state.get_repo(interaction.channel_id)
        if not repo:
            await interaction.followup.send(embed=formatter.format_no_repo())
            return
        try:
            result = await api_client.get_impact(repo["repo_path"], file)
            embed  = formatter.format_impact(result, repo["repo_name"], file)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(
                embed=formatter.format_error("Impact analysis failed", str(exc))
            )

    # ── /repobot arch ──────────────────────────────────────────────────────────

    @repobot.command(name="arch", description="Generate an architecture diagram of the loaded repo")
    async def cmd_arch(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        repo = state.get_repo(interaction.channel_id)
        if not repo:
            await interaction.followup.send(embed=formatter.format_no_repo())
            return
        try:
            result = await api_client.get_architecture(repo["repo_path"])

            # Portable identifier for the interactive deep link: prefer the
            # GitHub URL, fall back to the slug (repo_name), then the local path.
            repo_ref = repo.get("github_url") or repo.get("repo_name") or repo["repo_path"]

            # Try to render the diagram to a PNG and show it inline. If rendering
            # is unavailable, gracefully fall back to the text/code-block form.
            png = await api_client.render_mermaid_png(result.get("mermaid", ""))
            if png:
                image_file = discord.File(io.BytesIO(png), filename="architecture.png")
                embeds = formatter.format_architecture(
                    result, repo["repo_name"], repo_ref,
                    image_filename="architecture.png",
                )
                await interaction.followup.send(embed=embeds[0], file=image_file)
            else:
                embeds = formatter.format_architecture(
                    result, repo["repo_name"], repo_ref
                )
                await interaction.followup.send(embed=embeds[0])
                for extra in embeds[1:]:
                    await interaction.followup.send(embed=extra)
        except Exception as exc:
            await interaction.followup.send(
                embed=formatter.format_error("Architecture generation failed", str(exc))
            )

    # ── /repobot deadcode ──────────────────────────────────────────────────────

    @repobot.command(name="deadcode", description="Find files with no importers (potentially unused)")
    async def cmd_deadcode(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        repo = state.get_repo(interaction.channel_id)
        if not repo:
            await interaction.followup.send(embed=formatter.format_no_repo())
            return
        try:
            result = await api_client.get_dead_code(repo["repo_path"])
            embed  = formatter.format_dead_code(result, repo["repo_name"])
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(
                embed=formatter.format_error("Dead code detection failed", str(exc))
            )

    # ── /repobot onboard ───────────────────────────────────────────────────────

    @repobot.command(name="onboard", description="Generate a structured onboarding guide for new contributors")
    async def cmd_onboard(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        repo = state.get_repo(interaction.channel_id)
        if not repo:
            await interaction.followup.send(embed=formatter.format_no_repo())
            return
        try:
            result = await api_client.get_onboarding(repo["repo_path"])
            embeds = formatter.format_onboarding(result, repo["repo_name"])
            await interaction.followup.send(embed=embeds[0])
            for extra in embeds[1:]:
                await interaction.followup.send(embed=extra)
        except Exception as exc:
            await interaction.followup.send(
                embed=formatter.format_error("Onboarding generation failed", str(exc))
            )

    # ── /repobot status ────────────────────────────────────────────────────────

    @repobot.command(name="status", description="Show which repo is loaded in this channel")
    async def cmd_status(interaction: discord.Interaction):
        repo = state.get_repo(interaction.channel_id)
        if not repo:
            await interaction.response.send_message(embed=formatter.format_no_repo())
            return
        embed = discord.Embed(
            title="📌 Active Repository",
            colour=0x5865F2,
        )
        embed.add_field(name="Repo",       value=repo["repo_name"],  inline=False)
        embed.add_field(name="Path",       value=f'`{repo["repo_path"]}`', inline=False)
        embed.add_field(name="Index name", value=f'`{repo["index_name"]}`', inline=False)
        await interaction.response.send_message(embed=embed)

    # ── Register the group ─────────────────────────────────────────────────────
    tree.add_command(repobot)

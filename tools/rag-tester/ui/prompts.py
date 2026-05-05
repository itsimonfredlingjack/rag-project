"""
Prompts module for RAG-Eval Terminal.
Handles user interaction using prompt_toolkit.
"""


from prompt_toolkit.shortcuts import input_dialog, radiolist_dialog
from prompt_toolkit.styles import Style

# Define custom styles for prompt_toolkit to match our Colorful Neon theme
# Using ANSI standard colors or brighter hex to ensure visibility on all terminals
MODERN_STYLE = Style.from_dict(
    {
        "dialog": "bg:#2E004F #00ff00",  # Dark Violet background, Green Border
        "dialog.body": "bg:#4B0082 #ffffff",  # Indigo body, White text
        "dialog.shadow": "bg:#000000",  # Black shadow
        "button.focused": "bg:#00ffff #000000",  # Cyan focus
        "radio-list.focused": "bg:#00ffff #000000",
        "text-area": "bg:#4B0082 #ffffff",
    }
)


class MainMenu:
    """Handles the main menu interaction."""

    async def show(self) -> str:
        """Show the main menu and return choice."""
        # Using a simple input for menu to start, or prompt_toolkit shortcuts
        # A radiolist is good for menus
        result = await radiolist_dialog(
            title="RAG-Eval Terminal",
            text="Welcome back. Please select an operational mode:",
            values=[
                ("1", "random   [Random Question] 🎲"),
                ("2", "category [Select Category] 📂"),
                ("3", "custom   [Custom Question] ✍️"),
                ("4", "history  [View History]    📜"),
                ("q", "quit     [Exit System]     🚪"),
            ],
            style=MODERN_STYLE,
        ).run_async()
        return result


class CategorySelector:
    """Handles category selection."""

    async def select(self, categories: list[str]) -> str | None:
        """Show category selector."""
        values = [(c, f"📂 {c.upper()}") for c in categories]
        result = await radiolist_dialog(
            title="Select Category",
            text="Filter questions by knowledge domain:",
            values=values,
            style=MODERN_STYLE,
        ).run_async()
        return result


class RatingInput:
    """Handles rating input."""

    async def get_rating(self) -> tuple[int, str | None]:
        """Get rating (1-5) and comment."""
        # 1. Get Star Rating
        rating = None
        while rating is None:
            rating_str = await radiolist_dialog(
                title="Rate Answer",
                text="How would you rate the quality of this response?",
                values=[
                    (5, "⭐⭐⭐⭐⭐ Excellent"),
                    (4, "⭐⭐⭐⭐ Good"),
                    (3, "⭐⭐⭐ Satisfactory"),
                    (2, "⭐⭐ Needs Improvement"),
                    (1, "⭐ Poor"),
                ],
                style=MODERN_STYLE,
            ).run_async()

            if rating_str:
                rating = int(rating_str)
            else:
                # If cancelled
                return 0, None

        # 2. Get Comment
        comment = await input_dialog(
            title="Feedback",
            text="Optional: Add a comment or tag for this rating:",
            style=MODERN_STYLE,
        ).run_async()

        return rating, comment

    async def get_custom_question(self) -> str | None:
        """Get a custom question text."""
        return await input_dialog(
            title="Custom Question", text="Please enter your query:", style=MODERN_STYLE
        ).run_async()


class ActionMenu:
    """Handles post-query actions."""

    async def show(self) -> str:
        """Show action menu."""
        # Small delay to ensure previous input is processed/cleared
        import asyncio

        await asyncio.sleep(0.1)

        result = await radiolist_dialog(
            title="Action Menu",
            text="Result generated. Choose next step:",
            values=[
                ("rate", "📝 Rate & Save"),
                ("inspect", "🔍 Inspect Sources"),
                ("continue", "⏩ Continue"),
            ],
            style=MODERN_STYLE,
        ).run_async()
        return result

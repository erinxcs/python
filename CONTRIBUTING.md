# Contributing

Thanks for helping improve ERINX Python Games. Each game lives in its own folder under `Game/` and can be updated independently.

## Make a change

1. Choose a game and read its `README.md` for setup and controls.
2. Create a branch for your change:

   ```powershell
   git switch -c docs/improve-game-guide
   ```

3. Make one focused change. Good first contributions include correcting a README, clarifying controls, or fixing a small gameplay issue.
4. Run the game from its folder and check that your change works.
5. Review and commit your change:

   ```powershell
   git status
   git diff
   git add Game/ERINX_Boxing/README.md
   git commit -m "docs: clarify boxing game instructions"
   ```

   Replace the example file and commit message with the files and description for your change.
6. Push your branch to GitHub:

   ```powershell
   git push -u origin docs/improve-game-guide
   ```

7. Open the repository on GitHub and create a pull request from your branch. Describe what changed and how you checked it.

## Before committing

- Keep generated files, virtual environments, and personal settings out of commits.
- Check `git diff` so you know exactly what will be included.
- Keep commits focused on one change.

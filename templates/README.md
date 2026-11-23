# Starting a project from the template

1. Create a project directory and copy these three files into it:

   ```
   demorec.yaml   # canvas, voice, pacing, masking
   pages.yaml     # page URLs + semantic element names
   scenes.yaml    # narration + storyboard steps
   ```

2. Put your `root_url` in `demorec.yaml` and your first page in `pages.yaml`.

3. If the site shows a brand block you need to cover, probe for mask boxes:

   ```
   python scripts/demorec.py probe <project>
   ```

   Look at `shots/probe_*.png`, confirm the area by eye, and paste the union into
   `mask.boxes`.

4. Validate the selectors — **always do this before recording**:

   ```
   python scripts/demorec.py dry <project>
   ```

   It really walks the navigation and clicks through, so a broken selector fails
   in seconds instead of after a ten-minute recording.

5. Record:

   ```
   python scripts/demorec.py run <project>
   ```

   This is tts → record → audio → build in order.

6. Check a frame yourself:

   ```
   ffmpeg -ss 3 -i out/<output_name> -frames:v 1 check.png
   ```

   Confirm the mask covers what it should, there is no watermark, and no browser
   chrome is visible.

For a worked reference, see `examples/todomvc/`: two scenes, entirely YAML, runnable
as-is.

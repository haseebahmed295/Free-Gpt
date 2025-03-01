import os
import json
import re
import traceback
import threading
import asyncio
from g4f.client import AsyncClient
import bpy.props
import bpy
import g4f
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from .dependencies import Module_Updater
from .utils import create_models, setup_logger , wrap_prompt , append_error_as_comment , stream_response 
from .Settings import code_system_prompt , JSON_PATH , IMAGE_SYSTEM_PROMPT

import os
import json
import re
import traceback
import threading
from g4f.client import AsyncClient
import bpy
import g4f
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from .dependencies import Module_Updater
from .utils import create_models, setup_logger, wrap_prompt, append_error_as_comment, stream_response
from .Settings import code_system_prompt, JSON_PATH, IMAGE_SYSTEM_PROMPT


class G4F_OT_Callback(bpy.types.Operator):
    """Operator to handle AI generation tasks with progress monitoring in Blender."""
    
    bl_idname = "g4f.callback"
    bl_label = "Callback for Thread"
    bl_description = "Callback Model Operator"

    # --- Initialization ---
    def __init__(self):
        """Initialize thread-safe progress tracking."""
        self._progress = 0.0  # Thread-safe progress variable (0.0 to 1.0)
        self._progress_lock = threading.Lock()  # Lock for thread-safe progress updates

    # --- Class Methods ---
    @classmethod
    def poll(cls, context):
        """Check if the operator can be executed.

        Args:
            context: Blender context.

        Returns:
            bool: True if the operator can run, False otherwise.
        """
        return (not context.scene.g4f_button_pressed and 
                not Module_Updater.is_working and 
                context.scene.g4f_chat_input)

    # --- Main Execution Methods ---
    def execute(self, context):
        """Start the AI generation process in a separate thread.

        Args:
            context: Blender context.

        Returns:
            set: {'RUNNING_MODAL'} to indicate modal operation.
        """
        # Initialize logging and console
        self.logger = setup_logger()
        self.console = Console()
        self.logger.info("Starting new G4F callback operation")
        self.console.print("[bold cyan]Starting AI generation...[/bold cyan]")

        # Set up initial state
        context.scene.g4f_button_pressed = True
        with self._progress_lock:
            self._progress = 0.0
        context.scene.g4f_progress = 0.0  # Safe in main thread
        self.is_done = False
        self.code_buffers = []
        self.is_cancelled = False
        self.cancel_done = False
        self.error = None
        self._thread = None
        self._timer = None
        self.is_image_model = False

        # Get input data
        ai_model = context.scene.ai_models
        chat_input = context.scene.g4f_chat_input
        chat_history = context.scene.g4f_chat_history
        system_prompt = self.get_system_prompt(ai_model)

        # Launch generation thread
        self.logger.debug(f"Launching thread with model: {ai_model}, input length: {len(chat_input)}")
        self.console.print(f"[cyan]Using model:[/cyan] [italic]{ai_model}[/italic]")
        self._thread = threading.Thread(target=self.generate_g4f_code, args=(
            chat_input, chat_history, ai_model, system_prompt
        ))
        self._thread.start()

        # Set up modal timer
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        self.report({'INFO'}, 'Generating... (ESC=Abort)')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        """Handle modal events during generation.

        Args:
            context: Blender context.
            event: The event to process (e.g., 'TIMER', 'ESC').

        Returns:
            set: Status indicating how to proceed ('PASS_THROUGH', 'CANCELLED', 'FINISHED').
        """
        if event.type == 'ESC':
            self.logger.info("User requested abort via ESC key")
            self.console.print("[bold red]ESC pressed - Aborting operation...[/bold red]")
            self.report({'INFO'}, "Aborting...")
            self.is_cancelled = True
            return {'PASS_THROUGH'}

        if event.type == 'TIMER':
            with self._progress_lock:
                context.scene.g4f_progress = self._progress
            context.area.tag_redraw()  # Redraw UI to reflect progress
            if self.is_cancelled and self.cancel_done:
                self.cleanup(context)
                return {'CANCELLED'}
            if self.is_done and not self.is_cancelled:
                self.logger.debug("Operation completed, executing callback")
                self.console.print("[green]Generation complete, executing callback...[/green]")
                self.callback(context, self.code_buffers, self.is_image_model)
                self.cleanup(context)
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    # --- Generation Logic ---
    def generate_g4f_code(self, prompt, chat_history, model, system_prompt):
        """Generate AI response in a separate thread.

        Args:
            prompt (str): User input text.
            chat_history: Collection of previous chat messages.
            model (str): AI model name.
            system_prompt (str): System prompt for the AI.
        """
        self.logger.info("Starting generation")
        self.console.print("[blue]Generating response...[/blue]")

        # Format chat messages
        formatted_messages = [{"role": "system", "content": system_prompt}]
        for message in chat_history[-10:]:
            role = "assistant" if message.type == "assistant" else message.type.lower()
            content = f"```\n{message.content}\n```" if message.type == "assistant" else message.content
            formatted_messages.append({"role": role, "content": content})
        if self.is_image_model:
            formatted_messages.append({"role": "user", "content": prompt})
        else:
            formatted_messages.append({"role": "user", "content": wrap_prompt(prompt)})

        stream = g4f.models.ModelUtils.convert[model].best_provider.supports_stream

        try:
            client = g4f.client.Client()
            with self._progress_lock:
                self._progress = 0.1  # Initializing

            if stream:
                completion_text = ''
                self.logger.debug("Using streaming response")
                self.console.print("[magenta]Streaming response...[/magenta]")
                with Live(console=self.console, refresh_per_second=30, transient=False) as live:
                    chunk_count = 0
                    for chunk in stream_response(formatted_messages, model):
                        if self.is_cancelled:
                            self.logger.warning("Stream cancelled by user")
                            self.console.print("[yellow]Generation cancelled by user[/yellow]")
                            self.cancel_done = True
                            return
                        
                        # Parse chunk if it's in SSE format (data: {"content": "..."})
                        if isinstance(chunk, str):
                            if "data: " in chunk:
                                cleaned_chunk = chunk.replace("data: ", "").strip()
                                self.logger.debug(f"Raw chunk: {repr(chunk)} -> Cleaned: {repr(cleaned_chunk)}")
                                try:
                                    chunk_data = json.loads(cleaned_chunk)
                                    content = chunk_data.get("content", "")
                                    if content is None:  # Handle cases where content might be null
                                        content = ""
                                    self.logger.debug(f"Parsed chunk content: {repr(content)}")
                                except json.JSONDecodeError as e:
                                    self.logger.warning(f"Invalid chunk format: {repr(chunk)} - Error: {str(e)}")
                                    content = chunk  # Fallback to raw chunk
                            else:
                                content = chunk  # Plain text chunk

                        completion_text += content or ''
                        chunk_count += 1
                        with self._progress_lock:
                            # Dynamic progress: assume up to 0.7 during streaming
                            self._progress = min(0.7, 0.1 + (0.6 * (chunk_count / 100.0)))
                        markdown_output = Markdown(completion_text.strip())
                        live.update(markdown_output, refresh=True)
                    with self._progress_lock:
                        self._progress = 0.8  # Stream complete
                # print(completion_text)
            else:
                self.logger.debug("Using non-streaming response")
                self.console.print("[magenta]Generating non-streaming response...[/magenta]")
                with self._progress_lock:
                    self._progress = 0.3  # Sending request
                response = client.chat.completions.create(model=model, messages=formatted_messages)
                with self._progress_lock:
                    self._progress = 0.7  # Response received
                completion_text = str(response.choices[0].message.content)
                with self._progress_lock:
                    self._progress = 0.8  # Processing response
                self.console.print(Markdown(completion_text.strip()))
                if self.is_cancelled:
                    self.logger.warning("Non-streaming operation cancelled")
                    self.console.print("[yellow]Generation cancelled by user[/yellow]")
                    self.cancel_done = True
                    return

            # Process response into code buffers
            if self.is_image_model:
                self.code_buffers = [f"# Image Description:\n# {completion_text.strip()}"]
            else:
                code_blocks = re.findall(r'```(?:python)?\s*\n(.*?)\n```', completion_text, re.DOTALL)
                if not code_blocks:
                    code_blocks = re.findall(r'```(.*?)```', completion_text, re.DOTALL)
                self.code_buffers = ([re.sub(r'^python', '', code.strip(), flags=re.MULTILINE) 
                                    for code in code_blocks] if code_blocks else [completion_text])

            with self._progress_lock:
                self._progress = 0.9  # Finalizing
            self.logger.debug("Generation complete")
            self.console.print("[magenta]Generation completed[/magenta]")
            self.is_done = True

        except Exception as e:
            self.logger.error(f"Error in generation: {str(e)}\n{traceback.format_exc()}")
            self.console.print(f"[red]Error during generation:[/red] {str(e)}")
            self.error = e
            self.is_cancelled = True
            self.cancel_done = True

    # --- Helper Methods ---
    def get_system_prompt(self, model_name):
        """Determine the appropriate system prompt based on the model type.

        Args:
            model_name (str): Name of the AI model.

        Returns:
            str: System prompt (image or code-specific).
        """
        try:
            if os.path.exists(JSON_PATH):
                with open(JSON_PATH, 'r') as f:
                    config = json.load(f)
                    image_models = config.get('image_models', [])
                    if model_name in image_models:
                        self.is_image_model = True
                        self.logger.info(f"Detected image model: {model_name}")
                        self.console.print(f"[purple]Image model detected: {model_name}[/purple]")
                        return IMAGE_SYSTEM_PROMPT
            else:
                self.logger.warning("Model config file not found")
                self.console.print("[yellow]Model config file not found[/yellow]")
        except Exception as e:
            self.logger.error(f"Error reading JSON config: {str(e)}")
            self.console.print(f"[red]Error reading model config: {str(e)}[/red]")
        return code_system_prompt

    def callback(self, context, code_buffers, is_image_model):
        """Process the generated response and update Blender state.

        Args:
            context: Blender context.
            code_buffers (list): List of generated code or text blocks.
            is_image_model (bool): Whether the model is an image model.
        """
        if self.is_cancelled:
            self.logger.warning("Callback skipped due to cancellation")
            self.console.print("[yellow]Execution skipped due to cancellation[/yellow]")
            self.cancel_done = True
            return

        # Update chat history with user input
        self.logger.debug("Adding user message to chat history")
        self.console.print("[blue]Updating chat history...[/blue]")
        message = context.scene.g4f_chat_history.add()
        message.type = 'user'
        message.content = context.scene.g4f_chat_input
        context.scene.g4f_chat_input = ""

        if not code_buffers:
            self.logger.warning("No code buffers to process")
            self.console.print("[yellow]No code generated to execute[/yellow]")
            return

        if is_image_model:
            response_content = code_buffers[0]
            self.logger.info("Image description stored")
            self.console.print("[purple]Image description stored[/purple]")
        else:
            safe_builtins = globals().copy()
            local_namespace = {}

            executed_codes = []
            for i, blender_code in enumerate(code_buffers):
                if not blender_code.strip():
                    self.logger.debug(f"Skipping empty code block {i + 1}")
                    continue

                self.logger.info(f"Processing code block {i + 1}/{len(code_buffers)}")
                self.console.print(f"[green]Processing code block {i + 1}/{len(code_buffers)}...[/green]")

                # Optionally preview code before execution (configurable via scene property)
                if hasattr(context.scene, "g4f_preview_code") and context.scene.g4f_preview_code:
                    self.console.print(f"[cyan]Preview:[/cyan]\n```python\n{blender_code}\n```")
                    self.report({'INFO'}, f"Previewing code block {i + 1} - check console")
                    continue  # Skip execution in preview mode

                try:
                    # Compile first to catch syntax errors early
                    compiled_code = compile(blender_code, f"<AI_code_block_{i + 1}>", "exec")
                    
                    # Set up context override
                    override = bpy.context.copy()
                    override["selected_objects"] = list(bpy.context.scene.objects)
                    with context.temp_override(**override):
                        exec(compiled_code, safe_builtins, local_namespace)

                    self.logger.info(f"Code block {i + 1} executed successfully")
                    self.console.print(f"[bold green]Code block {i + 1} executed successfully[/bold green]")
                    executed_codes.append(blender_code)

                except SyntaxError as se:
                    error_msg = f"Syntax error in block {i + 1}: {str(se)}\nLine {se.lineno}: {se.text}"
                    self.logger.error(error_msg + f"\n{traceback.format_exc()}")
                    self.console.print(f"[red]{error_msg}[/red]")
                    failed_code = append_error_as_comment(blender_code, error_msg)
                    executed_codes.append(failed_code)
                    self.report({'ERROR'}, f"Syntax error in block {i + 1}: {se}")

                except Exception as e:
                    error_msg = f"Error executing block {i + 1}: {str(e)}"
                    self.logger.error(error_msg + f"\n{traceback.format_exc()}")
                    self.console.print(f"[red]{error_msg}[/red]")
                    full_traceback = traceback.format_exc()
                    failed_code = append_error_as_comment(blender_code, full_traceback)
                    executed_codes.append(failed_code)
                    self.report({'ERROR'}, error_msg)

            response_content = "\n\n".join(executed_codes) if executed_codes else code_buffers[0]

        # Add response to chat history
        self.logger.debug("Adding assistant response to chat history")
        self.console.print("[blue]Adding response to chat history[/blue]")
        message = context.scene.g4f_chat_history.add()
        message.type = 'assistant'
        message.content = response_content

        context.scene.g4f_button_pressed = False
        context.scene.g4f_progress = 1.0  # Mark completion
        self.is_done = True
        self.logger.info("Callback operation completed")
        self.console.print("[bold cyan]Operation completed[/bold cyan]")

    def cleanup(self, context):
        """Clean up resources after generation completes or is cancelled.

        Args:
            context: Blender context.
        """
        try:
            if self._timer is not None:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=1.0)
            context.scene.g4f_button_pressed = False
            context.scene.g4f_progress = 0.0
            with self._progress_lock:
                self._progress = 0.0
            self.code_buffers = []
            self.is_done = False
            self.is_cancelled = False
            self.cancel_done = False
            self.error = None
            self.is_image_model = False
            self.logger.info("Cleanup completed successfully")
            self.console.print("[yellow]Cleanup completed[/yellow]")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}")
            self.console.print(f"[red]Cleanup error:[/red] {str(e)}")
            self.report({'ERROR'}, f"Cleanup failed: {str(e)}")

class G4F_TEST_OT_TestModels(bpy.types.Operator):
    """Checks for working models and updates the list of active models.
    This operator is used to test all available models and update the list of active models.
    """
    bl_idname = "g4f.update_model_list"
    bl_label = "Test g4f Models"
    bl_options = {'REGISTER'}
    bl_description = "Test all available models and update the list of active models.\n This may take a while."

    _timer = None
    _loop = None
    _task = None
    working = []
    is_working = False
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return not (Module_Updater.is_working or G4F_TEST_OT_TestModels.is_working or context.scene.g4f_button_pressed) 

    def modal(self, context: bpy.types.Context, event: bpy.types.Event) -> set:
        """Handle timer events for asynchronous task completion."""

        if event.type == 'TIMER':
            self._loop.run_until_complete(asyncio.sleep(0))  # Process pending tasks
            
            if self._task.done():
                self.logger.debug("Task is done, cleaning up")
                context.window_manager.event_timer_remove(self._timer)
                self._loop.stop()
                self._loop.close()
                
                non_working_models = set(g4f.models._all_models) - set(self.working)
                non_working_models = list(non_working_models)
                self.logger.info(f"Non-working models: {non_working_models}")
                
                path = JSON_PATH
                
                if not os.path.exists(path):
                    self.logger.debug(f"Creating new JSON file at {path}")
                    with open(path, 'w') as f:
                        json.dump({"active": [], "deprecated": []}, f)
                
                with open(path) as f:
                    data = json.load(f)
                data["active"] = self.working
                data["deprecated"] = non_working_models
                with open(path, 'w') as f:
                    json.dump(data, f)
                    self.logger.info("Updated model information saved to JSON")
                
                create_models()
                context.area.tag_redraw()
                self.logger.debug("Redrawing context area")
                G4F_TEST_OT_TestModels.is_working = False
                self.logger.info("Model testing completed")

                return {'FINISHED'}
        return {'PASS_THROUGH'}

    async def run_provider(self, model):
        self.logger.debug(f"Testing model: {model}")
        try:
            client = AsyncClient()
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
            )
            self.logger.debug(f"{model}: {response.choices[0].message.content}")
            self.working.append(model)
        except Exception as e:
            self.logger.debug(f"{model} failed: {e}")

    async def run_all(self):
        print("Starting async model tests")
        calls = [self.run_provider(provider) for provider in g4f.models._all_models]
        await asyncio.gather(*calls)

    def execute(self, context):
        self.logger = setup_logger()
        self.logger.info("Starting model tests")
        
        # Reset lists
        self.working = []
        G4F_TEST_OT_TestModels.is_working = True
        
        # Create and set up a new event loop
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.logger.info("Created new event loop")
        self._task = self._loop.create_task(self.run_all())
        self.logger.info("Created task to run all models")
        
        # Start the modal timer
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        if self._loop and self._loop.is_running():
            self._loop.stop()
            self._loop.close()


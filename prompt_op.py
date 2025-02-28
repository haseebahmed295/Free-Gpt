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

class G4F_OT_Callback(bpy.types.Operator):
    bl_idname = "g4f.callback"
    bl_label = "Callback for Thread"
    bl_description = "Callback Model Operator"


    @classmethod
    def poll(cls, context):
        return not context.scene.g4f_button_pressed and not Module_Updater.is_working and context.scene.g4f_chat_input

    def modal(self, context, event: bpy.types.Event) -> set:
        if event.type == 'ESC':
            self.logger.info("User requested abort via ESC key")
            self.console.print("[bold red]ESC pressed - Aborting operation...[/bold red]")
            self.report({'INFO'}, "Aborting...")
            self.is_cancelled = True
            return {'PASS_THROUGH'}

        if event.type == 'TIMER':
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

    def execute(self, context):
        self.logger = setup_logger()
        self.console = Console()
        self.logger.info("Starting new G4F callback operation")
        self.console.print("[bold cyan]Starting AI generation...[/bold cyan]")
        context.scene.g4f_button_pressed = True
        self.is_done = False
        self.code_buffers = []
        self.is_cancelled = False
        self.cancel_done = False
        self.error = None
        self._thread = None
        self._timer = None
        self.is_image_model = False

        ai_model = context.scene.ai_models
        chat_input = context.scene.g4f_chat_input
        chat_history = context.scene.g4f_chat_history

        system_prompt = self.get_system_prompt(ai_model)
        
        self.logger.debug(f"Launching thread with model: {ai_model}, input length: {len(chat_input)}")
        self.console.print(f"[cyan]Using model:[/cyan] [italic]{ai_model}[/italic]")
        self._thread = threading.Thread(target=self.generate_g4f_code, args=(
            chat_input, chat_history, ai_model, system_prompt
        ))
        self._thread.start()
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        self.report({'INFO'}, 'Generating... (ESC=Abort)')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def get_system_prompt(self, model_name):
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

    def generate_g4f_code(self, prompt, chat_history, model, system_prompt):
        self.logger.info("Starting generation")
        self.console.print("[blue]Generating response...[/blue]")
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
            if stream:
                completion_text = ''
                self.logger.debug("Using streaming response")
                self.console.print("[magenta]Streaming response...[/magenta]")
                
                with Live(console=self.console, refresh_per_second=30, transient=False) as live:
                    for chunk in stream_response(formatted_messages, model):
                        if self.is_cancelled:
                            self.logger.warning("Stream cancelled by user")
                            self.console.print("[yellow]Generation cancelled by user[/yellow]")
                            self.cancel_done = True
                            return
                        completion_text += chunk or ''
                        markdown_output = Markdown(completion_text.strip())
                        live.update(markdown_output, refresh=True)
            else:
                self.logger.debug("Using non-streaming response")
                self.console.print("[magenta]Generating non-streaming response...[/magenta]")
                response = client.chat.completions.create(
                    model=model, 
                    messages=formatted_messages
                )
                completion_text = str(response.choices[0].message.content)
                markdown_output = Markdown(completion_text.strip())
                self.console.print(markdown_output)
                
                if self.is_cancelled:
                    self.logger.warning("Non-streaming operation cancelled")
                    self.console.print("[yellow]Generation cancelled by user[/yellow]")
                    self.cancel_done = True
                    return

            # Process response based on model type
            if self.is_image_model:
                # For image models, store the description directly
                self.code_buffers = [f"# Image Description:\n# {completion_text.strip()}"]
                self.logger.info("Image model description generated")
                self.console.print("[purple]Image description generated[/purple]")
                
            else:
                # Handle code blocks for non-image models
                code_blocks = re.findall(r'```(?:python)?\s*\n(.*?)\n```', completion_text, re.DOTALL)
                if not code_blocks:
                    # Fallback to broader detection if no specific python blocks
                    code_blocks = re.findall(r'```(.*?)```', completion_text, re.DOTALL)
                
                if not code_blocks:
                    self.logger.warning("No code blocks found in response")
                    self.console.print("[yellow]No executable code blocks found[/yellow]")
                    self.code_buffers = [completion_text]
                else:
                    self.code_buffers = [re.sub(r'^python', '', code.strip(), flags=re.MULTILINE) 
                                      for code in code_blocks]
                    self.logger.info(f"Found {len(code_blocks)} code block(s)")
                    self.console.print(f"[green]Found {len(code_blocks)} code block(s)[/green]")

            self.logger.debug("Generation complete")
            self.console.print("[magenta]Generation completed[/magenta]")
            self.is_done = True

        except Exception as e:
            self.logger.error(f"Error in generation: {str(e)}\n{traceback.format_exc()}")
            self.console.print(f"[red]Error during generation:[/red] {str(e)}")
            self.error = e
            self.is_cancelled = True
            self.cancel_done = True

    def callback(self, context, code_buffers, is_image_model):
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

        if code_buffers:
            if not is_image_model:
                global_namespace = globals().copy()
                executed_codes = []
                
                for i, blender_code in enumerate(code_buffers):
                    if not blender_code.strip():
                        continue
                        
                    self.logger.info(f"Processing code block {i + 1}")
                    self.console.print(f"[green]Processing code block {i + 1}/{len(code_buffers)}...[/green]")
                    
                    try:
                        override = bpy.context.copy()
                        override["selected_objects"] = list(bpy.context.scene.objects)
                        with context.temp_override(**override):
                            exec(blender_code, global_namespace)
                        self.logger.info(f"Code block {i + 1} executed successfully")
                        self.console.print(f"[bold green]Code block {i + 1} executed successfully[/bold green]")
                        executed_codes.append(blender_code)
                    except Exception as e:
                        self.logger.error(f"Error executing code block {i + 1}: {str(e)}\n{traceback.format_exc()}")
                        self.console.print(f"[red]Error in code block {i + 1}:[/red] {str(e)}")
                        error = traceback.format_exc()
                        failed_code = append_error_as_comment(blender_code, error)
                        executed_codes.append(failed_code)
                        self.report({'ERROR'}, f"Error in code block {i + 1}: {e}")
                
                response_content = "\n\n".join(executed_codes) if executed_codes else code_buffers[0]
            else:
                response_content = code_buffers[0]
                self.logger.info("Image description stored")
                self.console.print("[purple]Image description stored[/purple]")

            # Add response to chat history
            self.logger.debug("Adding assistant response to chat history")
            self.console.print("[blue]Adding response to chat history[/blue]")
            message = context.scene.g4f_chat_history.add()
            message.type = 'assistant'
            message.content = response_content

        context.scene.g4f_button_pressed = False
        self.is_done = True
        self.logger.info("Callback operation completed")
        self.console.print("[bold cyan]Operation completed[/bold cyan]")

    def cleanup(self, context):
        try:
            if self._timer is not None:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            
            if self._thread is not None and self._thread.is_alive():
                self.logger.debug("Waiting for thread to complete during cleanup")
                self._thread.join(timeout=1.0)
            
            context.scene.g4f_button_pressed = False
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


import re
import traceback
import bpy
import bpy.props
import threading
import g4f
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from .dependencies import Module_Updater
from .utils import setup_logger , wrap_prompt , append_error_as_comment , stream_response
from .system_commad import system_prompt

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
                context.scene.g4f_button_pressed = False
                if self.error:
                    self.logger.error(f"Operation cancelled with error: {self.error}")
                    self.console.print(f"[red]Error during cancellation:[/red] {self.error}")
                    self.report({'ERROR'}, str(self.error))
                self.logger.info("Operation aborted successfully")
                self.console.print("[yellow]Operation aborted successfully[/yellow]")
                self.report({'INFO'}, "Aborted Successfully")
                return {'CANCELLED'}
            if self.is_done and not self.is_cancelled:
                self.logger.debug("Operation completed, executing callback")
                self.console.print("[green]Generation complete, executing code...[/green]")
                self.callback(context, self.code_buffer)
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    def execute(self, context):
        
        self.logger = setup_logger()
        self.console = Console()
        self.logger.info("Starting new G4F callback operation")
        self.console.print("[bold cyan]Starting AI code generation...[/bold cyan]")
        context.scene.g4f_button_pressed = True
        self.is_done = False
        self.code_buffer = None
        self.is_cancelled = False
        self.cancel_done = False
        self.error = None

        ai_model = context.scene.ai_models
        chat_input = context.scene.g4f_chat_input
        chat_history = context.scene.g4f_chat_history

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

    def generate_g4f_code(self, prompt, chat_history, model, system_prompt):
        self.logger.info("Starting code generation")
        self.console.print("[blue]Generating code...[/blue]")
        formatted_messages = [{"role": "system", "content": system_prompt}]
        for message in chat_history[-10:]:
            role = "assistant" if message.type == "assistant" else message.type.lower()
            content = f"```\n{message.content}\n```" if message.type == "assistant" else message.content
            formatted_messages.append({"role": role, "content": content})
        formatted_messages.append({"role": "user", "content": wrap_prompt(prompt)})

        stream = g4f.models.ModelUtils.convert[model].best_provider.supports_stream

        try:
            if stream:
                completion_text = '' 
                self.logger.debug("Using streaming response")
                self.console.print("[magenta]Streaming response...[/magenta]")
                
                with Live(console=self.console, refresh_per_second=30, transient=False,auto_refresh=True) as live:
                    for chunk in stream_response(formatted_messages, model):
                        if self.is_cancelled:
                            self.logger.warning("Stream cancelled by user")
                            self.console.print("[yellow]Generation cancelled by user[/yellow]")
                            self.cancel_done = True
                            return
                        completion_text += chunk or ''
                        markdown_output = Markdown(completion_text.strip())
                        live.update(markdown_output , refresh=True)
                
                self.logger.debug("Streaming complete")
                self.console.print("\n[magenta]Streaming completed[/magenta]")
            else:
                self.logger.debug("Using non-streaming response")
                self.console.print("[magenta]Generating non-streaming response...[/magenta]")
                client = g4f.client.Client()
                completion_text = str(client.chat.completions.create(
                    model=model, messages=formatted_messages))
                
                if self.is_cancelled:
                    self.logger.warning("Non-streaming operation cancelled")
                    self.console.print("[yellow]Generation cancelled by user[/yellow]")
                    self.cancel_done = True
                    return

            code = re.findall(r'```(.*?)```', completion_text, re.DOTALL)[0]
            self.code_buffer = re.sub(r'^python', '', code, flags=re.MULTILINE)
            self.logger.info("Code generated successfully")
            self.console.print("[green]Code generated successfully[/green]")
            self.is_done = True

        except Exception as e:
            self.logger.error(f"Error in code generation: {str(e)}\n{traceback.format_exc()}")
            self.console.print(f"[red]Error during generation:[/red] {str(e)}")
            self.error = e
            self.is_cancelled = True
            self.cancel_done = True

    def callback(self, context, output):
        if self.is_cancelled:
            self.logger.warning("Callback skipped due to cancellation")
            self.console.print("[yellow]Execution skipped due to cancellation[/yellow]")
            self.cancel_done = True
            return

        blender_code = output
        self.logger.debug("Adding user message to chat history")
        self.console.print("[blue]Updating chat history...[/blue]")
        message = context.scene.g4f_chat_history.add()
        message.type = 'user'
        message.content = context.scene.g4f_chat_input
        context.scene.g4f_chat_input = ""

        if blender_code:
            global_namespace = globals().copy()
            try:
                self.logger.info("Executing generated Blender code")
                self.console.print("[green]Executing generated code in Blender...[/green]")
                override = bpy.context.copy()
                override["selected_objects"] = list(bpy.context.scene.objects)
                with context.temp_override(**override):
                    exec(blender_code, global_namespace)
                self.logger.info("Code executed successfully")
                self.console.print("[bold green]Code executed successfully[/bold green]")
            except Exception as e:
                self.logger.error(f"Error executing code: {str(e)}\n{traceback.format_exc()}")
                self.console.print(f"[red]Error executing code:[/red] {str(e)}")
                self.report({'ERROR'}, f"Error executing code from AI: {e}")
                error = traceback.format_exc()
                blender_code = append_error_as_comment(blender_code, error)
            finally:
                self.logger.debug("Adding assistant response to chat history")
                self.console.print("[blue]Adding response to chat history[/blue]")
                message = context.scene.g4f_chat_history.add()
                message.type = 'assistant'
                message.content = blender_code

        context.scene.g4f_button_pressed = False
        self.is_done = True
        self.logger.info("Callback operation completed")
        self.console.print("[bold cyan]Operation completed[/bold cyan]")


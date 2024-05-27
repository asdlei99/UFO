# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.


import json
import traceback
from abc import ABC, abstractmethod
from typing import List

from pywinauto.controls.uiawrapper import UIAWrapper

from ufo import utils
from ufo.automator.ui_control.inspector import ControlInspectorFacade
from ufo.automator.ui_control.screenshot import PhotographerFacade
from ufo.config.config import Config
from ufo.module.state import Status
from ufo.modules.context import Context, ContextNames
from ufo.agents.basic import BasicAgent

configs = Config.get_instance().config_data
BACKEND = configs["CONTROL_BACKEND"]


class BaseProcessor(ABC):
    """
    The base processor for the session. A session consists of multiple rounds of conversation with the user, completing a task.
    At each round, the HostAgent and AppAgent interact with the user and the application with the processor.
    Each processor is responsible for processing the user request and updating the HostAgent and AppAgent at a single step in a round.
    """

    def __init__(self, agent: BasicAgent, context: Context) -> None:
        """
        Initialize the processor.
        :param context: The context of the session.
        :param agent: The agent who executes the processor.
        """

        self._context = context
        self._init_processor_from_context()

        self.photographer = PhotographerFacade()
        self.control_inspector = ControlInspectorFacade(BACKEND)

        self._step = 0
        self._prompt_message = None
        self._response = None
        self._cost = 0
        self._control_label = None
        self._control_text = None
        self._response_json = {}
        self._results = None
        self.app_root = None

    def process(self) -> None:
        """
        Process a single step in a round.
        The process includes the following steps:
        1. Print the step information.
        2. Capture the screenshot.
        3. Get the control information.
        4. Get the prompt message.
        5. Get the response.
        6. Parse the response.
        7. Execute the action.
        8. Update the memory.
        9. Create the app agent if necessary.
        10. Update the step and status.
        """

        # Step 1: Print the step information.
        self.print_step_info()

        # Step 2: Capture the screenshot.
        self.capture_screenshot()

        # Step 3: Get the control information.
        self.get_control_info()

        # Step 4: Get the prompt message.
        self.get_prompt_message()

        # Step 5: Get the response.
        self.get_response()

        if self.is_error():
            return

        # Step 6: Parse the response, if there is no error.
        self.parse_response()

        if self.is_error():
            return

        # Step 7: Execute the action.
        self.execute_action()

        # Step 8: Update the memory.
        self.update_memory()

        # Step 9: Create the app agent if necessary.
        if self.should_create_subagent():
            self.create_sub_agent()

        # Step 10: Update the step and status.
        self.update_step_and_status()

    @abstractmethod
    def print_step_info(self) -> None:
        """
        Print the step information.
        """
        pass

    @abstractmethod
    def capture_screenshot(self) -> None:
        """
        Capture the screenshot.
        """
        pass

    @abstractmethod
    def get_control_info(self) -> None:
        """
        Get the control information.
        """
        pass

    @abstractmethod
    def get_prompt_message(self) -> None:
        """
        Get the prompt message.
        """
        pass

    @abstractmethod
    def get_response(self) -> None:
        """
        Get the response from the LLM.
        """
        pass

    @abstractmethod
    def parse_response(self) -> None:
        """
        Parse the response.
        """
        pass

    @abstractmethod
    def execute_action(self) -> None:
        """
        Execute the action.
        """
        pass

    @abstractmethod
    def update_memory(self) -> None:
        """
        Update the memory of the Agent.
        """
        pass

    @abstractmethod
    def update_status(self) -> None:
        """
        Update the status of the session.
        """
        pass

    @property
    def context(self) -> Context:
        """
        Get the context.
        :return: The context.
        """
        return self._context

    def _init_processor_from_context(self) -> None:
        """
        Initialize the processor from the context.
        """

        self.log_path = self.context.get(ContextNames.LOG_PATH)
        self.request = self.context.get(ContextNames.REQUEST)
        self.request_logger = self.context.get(ContextNames.REQUEST_LOGGER)
        self.logger = self.context.get(ContextNames.LOGGER)
        self.round_step = self.context.get(ContextNames.ROUND_STEP)
        self.session_step = self.context.get(ContextNames.SESSION_STEP)
        self.prev_status = self.context.get(ContextNames.STATE)
        self.round_num = self.context.get(ContextNames.ROUND_NUMBER)
        self._app_window = self.context.get(ContextNames.APPLICATION_WINDOW)
        self.application_process_name = self.context.get(
            ContextNames.APPLICATION_PROCESS_NAME
        )

    def create_sub_agent(self) -> None:
        """
        Create the app agent.
        """
        pass

    def update_step_and_status(self) -> None:
        """
        Update the step and status of the process.
        """
        self._step += 1
        self.update_status()

    def get_active_window(self) -> UIAWrapper:
        """
        Get the active window.
        :return: The active window.
        """
        return self._app_window

    def get_active_control_text(self) -> str:
        """
        Get the active application.
        :return: The active application.
        """
        return self._control_text

    def get_process_status(self) -> str:
        """
        Get the process status.
        :return: The process status.
        """
        return self._status

    def get_process_step(self) -> int:
        """
        Get the process step.
        :return: The process step.
        """
        return self._step

    def get_process_cost(self) -> float:
        """
        Get the process cost.
        :return: The process cost.
        """
        return self._cost

    def is_error(self) -> bool:
        """
        Check if the process is in error.
        :return: The boolean value indicating if the process is in error.
        """

        return self._status == Status.ERROR

    def should_create_subagent(self) -> bool:
        """
        Check if the app agent should be created.
        :return: The boolean value indicating if the app agent should be created.
        """

        return False

    def log(self, response_json: dict) -> None:
        """
        Set the result of the session, and log the result.
        result: The result of the session.
        response_json: The response json.
        return: The response json.
        """

        self.logger.info(json.dumps(response_json))

    def error_log(self, response_str: str, error: str) -> None:
        """
        Error handler for the session.
        """
        log = json.dumps(
            {
                "step": self._step,
                "status": Status.ERROR,
                "response": response_str,
                "error": error,
            }
        )
        self.logger.info(log)

    @property
    def name(self) -> str:
        """
        Get the name of the processor.
        :return: The name of the processor.
        """
        return self.__class__.__name__

    def general_error_handler(self) -> None:
        """
        Error handler for the general error.
        """
        error_trace = traceback.format_exc()
        utils.print_with_color(f"Error Occurs at {self.name}", "red")
        utils.print_with_color(str(error_trace), "red")
        utils.print_with_color(self._response, "red")
        self.error_log(self._response, str(error_trace))
        self._status = Status.ERROR

    def llm_error_handler(self) -> None:
        """
        Error handler for the LLM error.
        """
        error_trace = traceback.format_exc()
        log = json.dumps(
            {
                "step": self.session_step,
                "prompt": self._prompt_message,
                "status": str(error_trace),
            }
        )
        utils.print_with_color(
            "Error occurs when calling LLM: {e}".format(e=str(error_trace)), "red"
        )
        self.request_logger.info(log)
        self._status = Status.ERROR
        return

    @staticmethod
    def string2list(string: str) -> List[str]:
        """
        Convert a string to a list of string if the input is a string.
        :param string: The string.
        :return: The list.
        """
        if isinstance(string, str):
            return [string]
        else:
            return string

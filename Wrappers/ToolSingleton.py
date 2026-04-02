from Wrappers.ToolWrapper import ToolWrapper


class ToolSingleton:
    tool_wrapper: ToolWrapper = None

    @staticmethod
    def set_tool_wrapper(tool_wrapper: ToolWrapper):
        ToolSingleton.tool_wrapper = tool_wrapper
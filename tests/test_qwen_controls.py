import unittest
from unittest.mock import patch

from agent.qwen import QwenModel
from agent.tool_index import ToolVectorIndex
from agent.tools.plugins.environment.tool import get_device_location
from agent.tools.plugins.simulated_home.tool import get_temperature, set_fan, set_light


class StaticRetriever:
    def top_five(self, text):
        return [{"name": "set_light", "x_chinese": {"name": "设置灯光"}}]


class StubQwen(QwenModel):
    def _post(self, path, body):
        self.prompt = body["messages"][0]["content"]
        return {"content": '{"function_calls":[{"name":"set_light","arguments":{"room":"bedroom","brightness":40}}]}'}


class CityChainQwen(QwenModel):
    def __init__(self):
        super().__init__("http://127.0.0.1:8080", StaticRetriever())
        self.responses = [
            '{"function_calls":[{"name":"resolve_city","arguments":{"city":"南京"}}]}',
            '{"function_calls":[{"name":"get_weather","arguments":{"city":"南京","latitude":32.06,"longitude":118.79}}]}',
        ]

    def _post(self, path, body):
        return {"content": self.responses.pop(0)}


class MixedLocationQwen(QwenModel):
    def __init__(self):
        super().__init__("http://127.0.0.1:8080", StaticRetriever())
        self.responses = [
            '{"function_calls":[{"name":"get_device_location","arguments":{"device":"living_room_sensor"}},{"name":"get_weather","arguments":{"city":"guessed"}}]}',
            '{"function_calls":[{"name":"get_device_location","arguments":{"device":"living_room_sensor"}},{"name":"get_weather","arguments":{"city":"南京","latitude":32.06,"longitude":118.79}}]}',
        ]

    def _post(self, path, body):
        return {"content": self.responses.pop(0)}


class QwenControlsTests(unittest.TestCase):
    def test_embedding_index_accepts_llama_cpp_list_response(self):
        class Response:
            def read(self):
                return b'[{"index":0,"embedding":[[0.1,0.2]]}]'
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False

        with patch("agent.tool_index.urlopen", return_value=Response()):
            index = ToolVectorIndex("http://local", [{"name": "demo"}])

        self.assertEqual(index.vectors, [[0.1, 0.2]])

    def test_qwen_prompt_supports_chinese_commands(self):
        model = StubQwen("http://127.0.0.1:8080", StaticRetriever())

        response = model.plan("打开卧室灯，亮度 40%")

        self.assertEqual(response["function_calls"][0]["arguments"]["room"], "bedroom")
        self.assertIn("设备天气", model.prompt)
        self.assertIn("x_chinese", model.prompt)

    def test_simulated_home_accepts_chinese_room_names_and_off_actions(self):
        self.assertEqual(set_light("卧室", 0).message, "卧室灯已关闭")
        self.assertEqual(set_fan("客厅", 0).message, "客厅风扇已关闭")
        self.assertEqual(get_temperature("厨房").data["room"], "厨房")

    def test_city_resolution_can_continue_once_to_weather(self):
        model = CityChainQwen()
        first = model.plan("南京的天气怎么样")
        second = model.feed_results([{"ok": True, "event": "city.resolve", "data": {"city": "南京", "latitude": 32.06, "longitude": 118.79}}])
        final = model.feed_results([{"ok": True, "event": "weather.read"}])

        self.assertEqual(first["function_calls"][0]["name"], "resolve_city")
        self.assertEqual(second["function_calls"][0]["name"], "get_weather")
        self.assertEqual(final["function_calls"], [])

    def test_simulated_device_location_uses_chinese_device_name(self):
        location = get_device_location("客厅设备")

        self.assertTrue(location.ok)
        self.assertEqual(location.event, "device.location.read")
        self.assertEqual(location.data["city"], "南京")

    def test_location_workflow_rejects_guessed_weather_arguments(self):
        model = MixedLocationQwen()
        first = model.plan("客厅设备当前位置天气")
        second = model.feed_results([{"ok": True, "event": "device.location.read", "data": {"city": "南京"}}])

        self.assertEqual([call["name"] for call in first["function_calls"]], ["get_device_location"])
        self.assertEqual([call["name"] for call in second["function_calls"]], ["get_weather"])


if __name__ == "__main__":
    unittest.main()

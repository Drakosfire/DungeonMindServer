"""Actual SERVER consumers through pinned GE; only external IO is faked.

Run with --noconftest to avoid full-app/live Firestore composition. These
witnesses cover dependency compatibility, not HTTP auth or deployed providers.
"""

import asyncio
import importlib
import json
import sys
from io import BytesIO
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image
from generationengine import GenerationClient, InferenceProfile
from generationengine.providers.openai_text import OpenAITextProvider


class RecordingResponses:
    def __init__(self, text):
        self.text = text
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self.text, model=kwargs["model"], id="resp_fake",
            _request_id="req_fake", refusal=None,
            usage=SimpleNamespace(input_tokens=11, output_tokens=3,
                                  input_tokens_details=SimpleNamespace(cached_tokens=0)),
        )


class RecordingImages:
    def __init__(self):
        self.calls = []
        self.blobs = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        image = Image.new("RGB", kwargs["size"], "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        self.blobs = [buffer.getvalue()] * kwargs["num_images"]
        return self.blobs


class RecordingClient(GenerationClient):
    """Capture public requests, then execute the real GE implementation."""
    def __init__(self, text=""):
        self.responses = RecordingResponses(text)
        self.provider_images = RecordingImages()
        self.requests = []
        super().__init__(text_provider=OpenAITextProvider(
            client=SimpleNamespace(responses=self.responses)),
            image_provider=self.provider_images)

    async def generate_text(self, request):
        self.requests.append(request)
        return await super().generate_text(request)

    async def generate_structured(self, request):
        self.requests.append(request)
        return await super().generate_structured(request)

    async def generate_image(self, request):
        self.requests.append(request)
        return await super().generate_image(request)

    async def edit_image(self, request):
        self.requests.append(request)
        return await super().edit_image(request)


@pytest.fixture(autouse=True)
def offline_configuration(monkeypatch):
    # R2 constructs a client on import; dummy explicit credentials prevent
    # metadata discovery. No R2 method is called. Never load a live env file.
    for key, value in {
        "R2_ACCESS_KEY_ID": "test", "R2_SECRET_ACCESS_KEY": "test",
        "CLOUDFLARE_ACCOUNT_ID": "test", "DUNGEONMIND_API_URL": "http://test",
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(key, value)
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)


def assert_text_request(client, *, profile, model, system, prompt, explicit_temperature):
    assert len(client.requests) == len(client.responses.calls) == 1
    request = client.requests[0]
    call = client.responses.calls[0]
    assert request.profile is profile
    assert request.model == model
    assert request.system_prompt == system
    assert request.user_prompt == prompt
    assert request.temperature == 0.7
    assert ("temperature" in request.model_fields_set) is explicit_temperature
    assert call["temperature"] == 0.7
    assert call["model"] == (model or "gpt-5.1")
    assert call["input"] == prompt
    if system:
        assert call["instructions"] == system
    else:
        assert "instructions" not in call
    return request


def mapspec_payload():
    from mapgenerator.models import MapSpec
    return MapSpec.model_validate({
        "meta": {"timestamp": "2026-01-01T00:00:00Z", "source_prompt": ""},
        "intent": {"summary": "A forest clearing", "location_type": "forest",
                   "tone": "neutral", "fantasy_level": "low"},
        "layout": {"scale": "encounter", "focal_point": "center",
                   "central_feature": "oak", "pathways": "organic"},
        "environment": {"terrain": ["grass"]},
        "style": {"rendering": "hand-painted", "palette": {}},
        "gameplay": {"movement_space": "open", "cover_density": "medium"},
        "constraints": {"forbid": ["watermarks"], "require": []},
    }).model_dump(mode="json")


def test_card_item_keeps_explicit_model_schema_prompt_and_default_sampling(monkeypatch):
    from cardgenerator.services import card_generation_service as consumer
    payload = {"Name": "Ferry Lantern", "Type": "Wondrous item", "Rarity": "Common",
               "Value": "10 gp", "Properties": ["Glows"], "Weight": "1 lb",
               "Description": "A brass lantern.", "Quote": "Homeward.",
               "SD Prompt": "A brass lantern", "Damage Formula": "", "Damage Type": ""}
    client = RecordingClient(json.dumps(payload))
    monkeypatch.setattr(consumer, "get_generation_client", lambda: client)
    service = consumer.CardGenerationService()
    idea = "a ferry lantern"
    expected_prompt = service.prompt_manager.render_prompt(
        template_name="item_generation", context={"item_name": idea})
    result = asyncio.run(service.generate_item_description(idea))
    assert result == {"Ferry Lantern": payload}
    request = assert_text_request(client, profile=InferenceProfile.STRUCTURED_LOW_COST,
                                  model="gpt-4o", system=None, prompt=expected_prompt,
                                  explicit_temperature=False)
    assert request.schema_name == "item"
    assert set(request.json_schema["properties"]) == set(payload)
    assert request.json_schema["required"] == [
        "Name", "Type", "Rarity", "Value", "Properties", "Weight", "Description", "Quote", "SD Prompt"]
    assert request.json_schema["additionalProperties"] is False
    assert request.json_schema["properties"]["Rarity"]["enum"] == [
        "Common", "Uncommon", "Rare", "Very Rare", "Legendary"]
    assert client.responses.calls[0]["text"]["format"]["name"] == "item"


def test_pcg_keeps_prompts_numeric_sampling_and_preference_interpretation(monkeypatch):
    from playercharactergenerator import pcg_generator as consumer
    from playercharactergenerator.models.pcg_models import PreferenceGenerationRequest
    payload = {"abilityPriorities": ["strength", "dexterity", "constitution",
                                     "intelligence", "wisdom", "charisma"],
               "equipmentStyle": "weathered steel",
               "character": {"name": "Mira", "personality": {"traits": ["patient"]},
                             "backstory": "A ferry guard."}}
    raw = json.dumps(payload)
    client = RecordingClient(raw)
    monkeypatch.setattr(consumer, "get_generation_client", lambda: client)
    service = consumer.PlayerCharacterGenerator()
    product_request = PreferenceGenerationRequest(
        input={"classId": "fighter", "raceId": "human", "level": 1,
               "backgroundId": "soldier", "concept": "A patient ferry guard"},
        constraints=consumer.create_mock_fighter_constraints())
    expected_prompt = service.prompt_manager.build_preference_prompt(
        product_request.input, product_request.constraints)
    success, result = asyncio.run(service.generate_preferences(product_request))
    assert success is True
    assert result["preferences"]["character"]["name"] == "Mira"
    assert result["preferences"]["abilityPriorities"] == payload["abilityPriorities"]
    assert result["rawResponse"] == raw
    assert {key: result["generationInfo"][key] for key in
            ("model", "promptTokens", "completionTokens", "totalTokens")} == {
                "model": "gpt-5.1", "promptTokens": 11, "completionTokens": 3, "totalTokens": 14}
    request = assert_text_request(client, profile=InferenceProfile.TEXT_FAST, model=None,
                                  system=service.prompt_manager.get_system_prompt(),
                                  prompt=expected_prompt, explicit_temperature=True)
    assert request.json_schema is None
    assert request.schema_name is None


def test_mapspec_keeps_schema_prompts_sampling_and_hard_constraints(monkeypatch):
    from mapgenerator import prompt_compiler as consumer
    client = RecordingClient(json.dumps(mapspec_payload()))
    monkeypatch.setattr(consumer, "get_generation_client", lambda: client)
    prompt, style, defaults = "A forest clearing", {"tone": "neutral"}, {"scale": "encounter"}
    result = asyncio.run(consumer.generate_mapspec(prompt, style, defaults))
    expected_prompt = (f"\nUSER_TEXT:\n<<<{prompt}>>>\n\nOPTIONAL_FIELDS:\n"
                       f"<<<{json.dumps(style)}>>>\n\nDEFAULTS:\n<<<{json.dumps(defaults)}>>>\n")
    request = assert_text_request(client, profile=InferenceProfile.STRUCTURED_LOW_COST,
                                  model=None, system=consumer.MAPSPEC_SYSTEM_PROMPT,
                                  prompt=expected_prompt, explicit_temperature=True)
    assert request.json_schema == consumer.MapSpec.model_json_schema()
    assert request.schema_name == "mapspec"
    assert client.responses.calls[0]["text"]["format"]["name"] == "mapspec"
    assert isinstance(result, consumer.MapSpec)
    assert result.meta.source_prompt == prompt
    assert result.layout.central_feature == "oak"
    assert set(consumer.HARD_CONSTRAINTS_FORBID) <= set(result.constraints.forbid)
    assert "watermarks" in result.constraints.forbid


def test_svg_keeps_prompts_sampling_and_extracts_valid_svg(monkeypatch):
    from mapgenerator import svg_mask as consumer
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 768 768"><rect width="768" height="768" fill="white"/></svg>'
    client = RecordingClient(f"```svg\n{svg}\n```")
    monkeypatch.setattr(consumer, "get_generation_client", lambda: client)
    description = "A square clearing"
    assert asyncio.run(consumer.generate_svg_from_description(description)) == svg
    request = assert_text_request(client, profile=InferenceProfile.TEXT_FAST, model=None,
                                  system=consumer.SVG_SYSTEM_PROMPT,
                                  prompt=consumer.SVG_USER_PROMPT_TEMPLATE.format(description=description),
                                  explicit_temperature=True)
    assert request.json_schema is None
    assert request.schema_name is None


def publication(monkeypatch, consumer):
    published = []

    async def publish(image):
        published.append(image)
        return SimpleNamespace(url=f"https://example.test/image/{len(published)}",
                               provider_image_id="fake-image", account_id="fake-account")

    monkeypatch.setattr(consumer, "publish_generated_image", publish)
    return published


@pytest.mark.parametrize("kind", ["core", "template"])
def test_card_images_keep_models_dimensions_and_publish_real_ge_results(monkeypatch, kind):
    from cardgenerator.services import card_generation_service as consumer
    client = RecordingClient()
    monkeypatch.setattr(consumer, "get_generation_client", lambda: client)
    published = publication(monkeypatch, consumer)
    service = consumer.CardGenerationService()
    prompt = "A brass lantern"
    if kind == "core":
        result = asyncio.run(service.generate_core_images(prompt, num_images=2))
        model, size, source = "nano-banana-pro", (1024, 1024), None
    else:
        source = "https://example.test/template.png"
        result = asyncio.run(service.generate_card_images(source, prompt, num_images=2))
        model, size = "flux-lora-i2i", (768, 1024)
        prompt = ("blank card, no text, blank textbox at top for title, mid for details and bottom for description, "
                  "detailed high quality thematic borders, A brass lantern in on a background of appropriate setting or location")
    request = client.requests[0]
    assert request.profile is InferenceProfile.IMAGE_HIGH_QUALITY
    assert request.model == model
    assert request.prompt == prompt
    assert request.num_images == 2
    assert (request.width, request.height) == size
    assert request.source_image_url == source
    assert request.strength == (0.85 if kind == "template" else None)
    assert client.provider_images.calls == [{
        "prompt": prompt, "model": model, "num_images": 2, "size": size,
        "image_url": source, "strength": 0.85, "mask_base64": None,
        "base_image_base64": None, "negative_prompt": None}]
    assert [image.content for image in published] == client.provider_images.blobs
    assert [(image.width, image.height) for image in published] == [size, size]
    assert all(image.media_type == "image/png" for image in published)
    assert result.success is True
    assert result.images == [{"url": "https://example.test/image/1"}, {"url": "https://example.test/image/2"}]


def test_inpainting_keeps_edit_contract_and_publishes_real_ge_result(monkeypatch):
    from mapgenerator import inpainting as consumer
    from security_limits.image_bounds import encode_image_data_uri
    client = RecordingClient()
    monkeypatch.setattr(consumer, "get_generation_client", lambda: client)
    published = publication(monkeypatch, consumer)
    base = encode_image_data_uri(Image.new("RGBA", (1024, 1024), "white"), fmt="PNG")
    url = asyncio.run(consumer.generate_inpainted_map(
        prompt="A forest path", mask_base64=base, base_image_base64=base, negative_prompt="text"))
    request = client.requests[0]
    assert request.profile is InferenceProfile.IMAGE_EDIT_HIGH_QUALITY
    assert request.model == "gpt-image-1.5"
    assert request.prompt == "A forest path"
    assert request.mask_base64 == request.base_image_base64 == base
    assert (request.width, request.height) == (1024, 1024)
    assert request.negative_prompt == "text"
    call = client.provider_images.calls[0]
    assert call["model"] == "gpt-image-1.5"
    assert call["mask_base64"] == call["base_image_base64"] == base
    assert call["negative_prompt"] == "text"
    assert published[0].content == client.provider_images.blobs[0]
    assert url == "https://example.test/image/1"


@pytest.fixture
def offline_routers(monkeypatch):
    # Isolate only the external Firestore bootstrap. Unexpected DB access fails;
    # actual router/auth/product modules and consumer bodies remain intact.
    class NoFirestore:
        def __getattr__(self, name):
            raise AssertionError(f"Unexpected Firestore access: {name}")

    module = ModuleType("firestore.firebase_config")
    module.db = NoFirestore()
    monkeypatch.setitem(sys.modules, "firestore.firebase_config", module)
    modules = []
    for name in ("routers.map_router", "routers.image_management_router"):
        # Do not leave a cached router containing the isolated bootstrap behind.
        monkeypatch.delitem(sys.modules, name, raising=False)
        modules.append(importlib.import_module(name))
    yield modules
    for module in modules:
        sys.modules.pop(module.__name__, None)


def isolate_route_io(monkeypatch, consumer):
    budget_calls, assets = [], []
    monkeypatch.setattr(consumer.paid_budget_store, "consume",
                        lambda owner, units: budget_calls.append((owner, units)))

    def register(**kwargs):
        assets.append(kwargs)
        return SimpleNamespace(asset_id="asset_fake")

    monkeypatch.setattr(consumer, "register_cloudflare_url_asset", register)
    return budget_calls, assets


def test_map_route_keeps_real_compilation_image_policy_and_response(monkeypatch, offline_routers):
    from auth_service import User
    from mapgenerator import prompt_compiler
    consumer = offline_routers[0]
    client = RecordingClient(json.dumps(mapspec_payload()))
    monkeypatch.setattr(consumer, "get_generation_client", lambda: client)
    monkeypatch.setattr(prompt_compiler, "get_generation_client", lambda: client)
    published = publication(monkeypatch, consumer)
    budgets, assets = isolate_route_io(monkeypatch, consumer)
    result = asyncio.run(consumer.generate_map(
        consumer.GenerateMapRequest(prompt="A forest clearing", width=512, height=1024),
        current_user=User(sub="user_fake", email="test@example.test", name="Test")))
    request = client.requests[1]
    assert len(client.requests) == 2  # Actual MapSpec text + image pipeline.
    assert request.profile is InferenceProfile.IMAGE_HIGH_QUALITY
    assert request.model == "gpt-image-1.5"
    assert request.prompt == result.compiled_prompt
    assert request.prompt == prompt_compiler.compile_image_prompt(
        prompt_compiler.MapSpec.model_validate(result.mapspec))
    assert (request.width, request.height) == (512, 1024)
    assert request.negative_prompt == ", ".join(result.mapspec["constraints"]["forbid"])
    assert client.provider_images.calls[0]["model"] == "gpt-image-1.5"
    assert published[0].content == client.provider_images.blobs[0]
    assert result.image_url == "https://example.test/image/1"
    assert result.asset_id == "asset_fake"
    assert (result.width, result.height) == (512, 1024)
    assert budgets == [("user_fake", 1)]
    assert assets[0]["owner_id"] == "user_fake"
    assert assets[0]["service"] == "map"


@pytest.mark.parametrize("model", ["flux-2-pro", "nano-banana-pro", "gpt-image-1.5"])
def test_image_route_keeps_selected_model_and_product_response(monkeypatch, offline_routers, model):
    from auth_service import User
    consumer = offline_routers[1]
    client = RecordingClient()
    monkeypatch.setattr(consumer, "get_generation_client", lambda: client)
    published = publication(monkeypatch, consumer)
    budgets, assets = isolate_route_io(monkeypatch, consumer)
    result = asyncio.run(consumer.generate_image(
        consumer.ImageGenerateRequest(prompt="A brass lantern", model=model, num_images=2),
        current_user=User(sub="user_fake", email="test@example.test", name="Test")))
    request = client.requests[0]
    assert request.profile is InferenceProfile.IMAGE_HIGH_QUALITY
    assert request.model == consumer.MODEL_MAP[model] == model
    assert request.prompt == "A brass lantern"
    assert request.num_images == 2
    assert (request.width, request.height) == (1024, 1024)
    assert client.provider_images.calls[0]["model"] == model
    assert [image.content for image in published] == client.provider_images.blobs
    assert result.success is True
    assert [image.url for image in result.data.images] == [
        "https://example.test/image/1", "https://example.test/image/2"]
    assert all(image.asset_id == "asset_fake" for image in result.data.images)
    assert result.data.generation_info.model == model
    assert result.data.generation_info.num_images == 2
    assert budgets == [("user_fake", 2)]
    assert len(assets) == 2
    assert all(asset["owner_id"] == "user_fake" and asset["service"] == "images" for asset in assets)

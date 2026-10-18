"""Quality gates for executable handoff examples and unapproved output fields."""

import json
import re
import unittest
from pathlib import Path

from vietsafe.integration.api_contracts import ArtifactApiBundle
from vietsafe.integration.api_projection import build_artifact_api_bundle
from vietsafe.integration.context_contracts import IntegrationContext
from vietsafe.integration.context_guard import build_integration_context
from vietsafe.integration.contracts import DataForecastInput, ForecastOutput
from vietsafe.integration.end_to_end import run_contract_pipeline
from vietsafe.integration.errors import IntegrationContractError
from .helpers import output_payload
from .test_registry_routing import registry


class QualityHandoffTests(unittest.TestCase):
    def test_handoff_examples_validate_and_bind_to_actual_artifacts(self):
        path = Path(__file__).resolve().parents[2] / 'vietsafe/integration/INTEGRATION_HANDOFF.md'
        payloads = [json.loads(s) for s in re.findall(r'```json\n(.*?)\n```', path.read_text(), re.S)]
        self.assertEqual(len(payloads), 6)
        constructors = [DataForecastInput, ForecastOutput, ForecastOutput, ForecastOutput,
                        IntegrationContext, ArtifactApiBundle]
        objects = [cls(p) for cls, p in zip(constructors, payloads)]
        self.assertEqual(objects[0].to_dict()['lookback_steps'], 6)
        result = run_contract_pipeline(registry=registry(), mode='artifact', generated_at='2026-10-08T04:12:34Z')
        self.assertEqual(objects[4].to_json(), result.context.to_json())
        self.assertEqual(objects[5].to_json(), result.api_bundle.to_json())
        for forecast in objects[1:4]:
            context = build_integration_context(mode='artifact', map_network=result.map_network,
                routing_network=result.routing_network, forecasts=[forecast])
            api = build_artifact_api_bundle(context=context, map_network=result.map_network,
                forecasts=[forecast], generated_at='2026-10-08T04:12:34Z')
            self.assertEqual(api.to_dict()['forecasts'][0], forecast.to_dict())

    def test_flood_depth_not_approved_even_if_producer_declares_it(self):
        for declared in (False, True):
            p = output_payload()
            p['roads'][0]['flood_depth_cm'] = 12
            if declared:
                p['output_fields'].append('flood_depth_cm')
            with self.subTest(declared=declared), self.assertRaises(IntegrationContractError) as caught:
                ForecastOutput(p)
            self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')

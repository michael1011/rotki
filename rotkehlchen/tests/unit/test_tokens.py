from unittest.mock import patch

import pytest
import requests

from rotkehlchen.chain.ethereum.tokens import EthTokens
from rotkehlchen.chain.ethereum.types import string_to_ethereum_address
from rotkehlchen.chain.ethereum.utils import token_normalized_value
from rotkehlchen.constants.assets import A_MKR, A_OMG
from rotkehlchen.fval import FVal
from rotkehlchen.tests.utils.blockchain import mock_etherscan_query
from rotkehlchen.tests.utils.constants import A_GNO
from rotkehlchen.tests.utils.factories import make_ethereum_address


@pytest.fixture(name='ethtokens')
def fixture_ethtokens(ethereum_manager, database):
    return EthTokens(database, ethereum_manager)


def test_detect_tokens_for_addresses(ethtokens, inquirer):  # pylint: disable=unused-argument
    """
    Autodetect tokens of two addresses

    This is going to be a bit slow test since it actually queries etherscan without any mocks.
    By doing so we can test that the whole behavior with etherscan works fine and our
    chosen chunk length for it is also acceptable.

    USD price queries are mocked so we don't care about the result.
    Just check that all prices are included


    """
    addr1 = string_to_ethereum_address('0x8d89170b92b2Be2C08d57C48a7b190a2f146720f')
    addr2 = string_to_ethereum_address('0xB756AD52f3Bf74a7d24C67471E0887436936504C')
    ethtokens.detect_tokens(False, [addr1, addr2])
    result, token_usd_prices = ethtokens.query_tokens_for_addresses([addr1, addr2])
    assert len(result[addr1]) == 3
    balance = result[addr1][A_OMG]
    assert isinstance(balance, FVal)
    assert balance == FVal('0.036108311660753218')
    assert len(result[addr2]) >= 1

    assert len(token_usd_prices) == len(set(result[addr1].keys()).union(set(result[addr2].keys())))


def test_detected_tokens_cache(ethtokens, inquirer):  # pylint: disable=unused-argument
    """Test that a cache of the detected tokens is created and used at subsequent queries.

    Also test that the cache can be ignored and recreated with a forced redetection
    """
    addr1 = make_ethereum_address()
    addr2 = make_ethereum_address()
    eth_map = {addr1: {A_GNO: 5000, A_MKR: 4000}, addr2: {A_MKR: 6000}}
    etherscan_patch = mock_etherscan_query(
        eth_map=eth_map,
        etherscan=ethtokens.ethereum.etherscan,
        original_queries=None,
        original_requests_get=requests.get,
        extra_flags=None,
    )
    ethtokens_max_chunks_patch = patch(
        'rotkehlchen.chain.ethereum.tokens.ETHERSCAN_MAX_TOKEN_CHUNK_LENGTH',
        new=800,
    )

    with ethtokens_max_chunks_patch, etherscan_patch as etherscan_mock:
        # Initially autodetect the tokens at the first call
        ethtokens.detect_tokens(False, [addr1, addr2])
        result1, _ = ethtokens.query_tokens_for_addresses([addr1, addr2])
        initial_call_count = etherscan_mock.call_count

        # Then in second call autodetect queries should not have been made, and DB cache used
        ethtokens.detect_tokens(True, [addr1, addr2])
        result2, _ = ethtokens.query_tokens_for_addresses([addr1, addr2])
        call_count = etherscan_mock.call_count
        assert call_count == initial_call_count + 2

        # In the third call force re-detection
        ethtokens.detect_tokens(False, [addr1, addr2])
        result3, _ = ethtokens.query_tokens_for_addresses([addr1, addr2])
        call_count = etherscan_mock.call_count
        assert call_count == initial_call_count + 2 + initial_call_count

        assert result1 == result2 == result3
        assert len(result1) == len(eth_map)
        for key, entry in result1.items():
            eth_map_entry = eth_map[key]
            assert len(entry) == len(eth_map_entry)
            for token, val in entry.items():
                assert token_normalized_value(eth_map_entry[token], token) == val


@pytest.mark.parametrize('ignored_assets', [[A_GNO]])
def test_ignored_tokens_in_query(ethtokens, inquirer):  # pylint: disable=unused-argument
    """Test that if a token is ignored it's not included in the query"""
    addr1 = make_ethereum_address()
    addr2 = make_ethereum_address()
    eth_map = {addr1: {A_GNO: 5000, A_MKR: 4000}, addr2: {A_MKR: 6000}}
    etherscan_patch = mock_etherscan_query(
        eth_map=eth_map,
        etherscan=ethtokens.ethereum.etherscan,
        original_queries=None,
        original_requests_get=requests.get,
        extra_flags=None,
    )
    ethtokens_max_chunks_patch = patch(
        'rotkehlchen.chain.ethereum.tokens.ETHERSCAN_MAX_TOKEN_CHUNK_LENGTH',
        new=800,
    )

    with ethtokens_max_chunks_patch, etherscan_patch:
        ethtokens.detect_tokens(False, [addr1, addr2])
        result, _ = ethtokens.query_tokens_for_addresses([addr1, addr2])
        assert len(result[addr1]) == 1
        assert result[addr1][A_MKR] == FVal('4E-15')
        assert len(result[addr2]) == 1

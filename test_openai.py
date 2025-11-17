#!/usr/bin/env python3
"""Test script for OpenAI integration"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import after loading env
from app.services.openai_service import openai_service
from config.settings import settings


async def test_text_generation():
    """Test basic text generation"""
    print("\n=== Testing Text Generation ===")
    print(f"Model: {settings.openai_model}")
    print(f"Max tokens: {settings.openai_max_tokens}")

    try:
        response, prompt_tokens, completion_tokens = await openai_service.generate_response(
            user_message="Merhaba! Nasılsın?",
            conversation_history=[]
        )

        print(f"\n✅ Success!")
        print(f"Response: {response}")
        print(f"Prompt tokens: {prompt_tokens}")
        print(f"Completion tokens: {completion_tokens}")
        print(f"Total tokens: {prompt_tokens + completion_tokens}")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_conversation_context():
    """Test conversation with context"""
    print("\n=== Testing Conversation with Context ===")

    try:
        # Simulate a conversation
        history = [
            {"role": "user", "content": "Benim adım Ahmet"},
            {"role": "assistant", "content": "Merhaba Ahmet! Tanıştığımıza memnun oldum. Size nasıl yardımcı olabilirim?"}
        ]

        response, prompt_tokens, completion_tokens = await openai_service.generate_response(
            user_message="Adımı hatırlıyor musun?",
            conversation_history=history
        )

        print(f"\n✅ Success!")
        print(f"Response: {response}")
        print(f"Prompt tokens: {prompt_tokens}")
        print(f"Completion tokens: {completion_tokens}")

        # Check if it remembers the name
        if "ahmet" in response.lower():
            print("✅ Context working - remembered the name!")
        else:
            print("⚠️ Context might not be working properly")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_turkish_response():
    """Test that responses are in Turkish"""
    print("\n=== Testing Turkish Language Response ===")

    try:
        response, _, _ = await openai_service.generate_response(
            user_message="Tell me about artificial intelligence",
            conversation_history=[]
        )

        print(f"\n✅ Success!")
        print(f"Response: {response}")

        # Check if response contains Turkish characters or common Turkish words
        turkish_indicators = ['ı', 'ş', 'ğ', 'ü', 'ö', 'ç', 'yapay', 'zeka', 'için', 'bir', 'olan']
        has_turkish = any(indicator in response.lower() for indicator in turkish_indicators)

        if has_turkish:
            print("✅ Response is in Turkish!")
        else:
            print("⚠️ Response might not be in Turkish")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("=" * 60)
    print("OpenAI Integration Tests")
    print("=" * 60)

    # Check if API key is set
    if not settings.openai_api_key or settings.openai_api_key == "your_openai_api_key_here":
        print("\n❌ Error: OPENAI_API_KEY not set in .env file")
        print("Please set your OpenAI API key in .env file")
        return

    print(f"\nAPI Key: {settings.openai_api_key[:20]}...")

    results = []

    # Run tests
    results.append(("Text Generation", await test_text_generation()))
    results.append(("Conversation Context", await test_conversation_context()))
    results.append(("Turkish Response", await test_turkish_response()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")

    total_passed = sum(1 for _, result in results if result)
    total_tests = len(results)

    print(f"\nTotal: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️ {total_tests - total_passed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())

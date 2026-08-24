# from flask import Flask, request, jsonify
# from langchain.chat_models import AzureChatOpenAI
# from langchain.schema import HumanMessage
# from typing import Dict
# from difflib import SequenceMatcher
# import os


# app = Flask(__name__)

# # Azure OpenAI Configuration
# llm = AzureChatOpenAI(
#     deployment_name="AllegisGPT-4o",
#     model="gpt-4o",
#     temperature=0,
#     openai_api_key="2f6e41aa534f49908feb01c6de771d6b",
#     openai_api_base="https://ea-oai-sandbox.openai.azure.com/",
#     openai_api_version="2024-05-01-preview",
# )


# def calculate_similarity(text1: str, text2: str) -> float:
#     """Calculate text similarity ratio"""
#     return SequenceMatcher(None, text1, text2).ratio()


# class TextRefiner:
#     def get_completion(self, prompt: str) -> str:
#         """Get completion from Azure OpenAI"""
#         try:
#             messages = [HumanMessage(content=prompt)]
#             response = llm(messages)
#             return response.content.strip()
#         except Exception as e:
#             raise


# class MinimalChangeRefiner(TextRefiner):
#     """Approach : Single-pass minimal modification"""

#     def refine(self, input_text: str, context: str, input_language: str) -> Dict:
#         prompt = f"""
#         You are a context-aware text refinement expert. You have a translated text that needs minimal modifications to better fit its original context.

#         Original translated text: {input_text}
#         Required context: {context}
#         Language: {input_language}

#         Rules:
#         1. Make ONLY absolutely necessary changes
#         2. Preserve the original meaning
#         3. Only modify words/phrases that directly impact contextual accuracy
#         4. Keep the same tone and style
#         5. Provide the refined text only

#         Return only the refined text without explanations.
#         """

#         refined_text = self.get_completion(prompt)
#         similarity = calculate_similarity(input_text, refined_text)

#         return {
#             "refined_text": refined_text,
#             "similarity_score": similarity,
#         }


# @app.route('/refine', methods=['POST'])
# def refine_text():
#     try:
#         data = request.get_json()
#         required_fields = ['input_text', 'input_language']

#         if not all(field in data for field in required_fields):
#             return jsonify({'error': 'Missing required fields'}), 400

#         refiner = MinimalChangeRefiner()

#         result = refiner.refine(
#             data['input_text'],
#             data['context'],
#             data['language']
#         )

#         return jsonify(result['refined_text'])

#     except Exception as e:
#         return jsonify({'error': str(e)}), 500


# if __name__ == '__main__':
#     app.run(debug=True)

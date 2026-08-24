from langchain_openai import AzureChatOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_core.messages import SystemMessage, HumanMessage

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)

llm = AzureChatOpenAI(
    deployment_name="gpt-5.1",
    model="gpt-5.1",
    azure_ad_token_provider=token_provider,
    azure_endpoint="https://ai-hubdevaiocm273154123411.cognitiveservices.azure.com/",
    openai_api_version="2025-04-01-preview",
)

resp = llm.invoke([
    SystemMessage(content="You are terse."),
    HumanMessage(content="Say hello in English and Kannada.")
])

print(repr(resp.content))

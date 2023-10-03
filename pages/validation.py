import openai
import streamlit as st
import json
import pandas as pd

from streamlit_ace import st_ace
from langchain.memory import StreamlitChatMessageHistory
from langchain.memory import ConversationBufferMemory
from langchain.memory.chat_message_histories import StreamlitChatMessageHistory

from langchain.agents import create_sql_agent, AgentExecutor
from langchain.agents.agent_toolkits import SQLDatabaseToolkit
from langchain.sql_database import SQLDatabase
from langchain.llms.openai import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.agents.agent_types import AgentType
from langchain.prompts import PromptTemplate
from langchain.evaluation import load_evaluator

from langchain.callbacks import StreamlitCallbackHandler, HumanApprovalCallbackHandler
from prompts import en_prompt_template

st.header("Validation page")


models = ['gpt-3.5-turbo-instruct', 'gpt-3.5-turbo-16k', 'gpt-4']

msgs = StreamlitChatMessageHistory(key="chat_messages")
memory = ConversationBufferMemory(chat_memory=msgs)

llm = ChatOpenAI(model=models[1], temperature=0)

def initialize_connection():
    account_identifier = st.secrets["account_identifier"]
    user = st.secrets["user"]
    password = st.secrets["password"]
    database_name = st.secrets["database_name"]
    schema_name = st.secrets["schema_name"]
    warehouse_name = st.secrets["warehouse_name"]
    role_name = st.secrets["user"]
    conn_string = f"snowflake://{user}:{password}@{account_identifier}/{database_name}/{schema_name}?warehouse={warehouse_name}&role={role_name}"
    db = SQLDatabase.from_uri(conn_string)
    toolkit = SQLDatabaseToolkit(llm=llm, db=db)
    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10,
        agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        memory=memory,
    )
    return agent_executor, conn_string

agent_executor, conn_string = initialize_connection()   


gen_sql_prompt = en_prompt_template

# grab the validation.json file and loop through it to call agent_executor.run
# for each validation example

evaluator = load_evaluator("string_distance")
with open('validation.json', 'r') as f:
    data = json.load(f)

st.write('Data loaded')
st.balloons()

evaluation_output = {}

for i in range(len(data)):
    st.write(f"Question: {data[i]['question']}")
    prompt_formatted = gen_sql_prompt.format(context=data[i]['question'])
    try:
        response = agent_executor.run(input=prompt_formatted, memory=memory)
    except ValueError as e:
        response = str(e)
        if not response.startswith("Could not parse LLM output: `"):
            raise e
        response = response.removeprefix("Could not parse LLM output: `").removesuffix("`")
    except openai.InvalidRequestError as e:
        response = str(e)
        if response.startswith("InvalidRequestError: This model's maximum context length%"):
                response = "Model context length exceeded. Please try again."

    evaluation = evaluator.evaluate_strings(
    prediction=response,
    reference=data[i]['answer'],
    )
    st.write(f"Answer: {data[i]['answer']}")
    st.write(f"Prediction: {response}")
    st.write(evaluation)

    evaluation_output[i] = {
        "question": data[i]['question'],
        "answer": data[i]['answer'],
        "prediction": response,
        "evaluation": evaluation
    }

st.write("Evaluation complete")

df = pd.DataFrame.from_dict(evaluation_output, orient='index')

# change the 'evaluation' column to be called 'score' and extract the score from the dictionary in the column
df['score'] = df['evaluation'].apply(lambda x: x['score'])

st.write("Evaluation results:")

avg_score = df['score'].mean()

st.metric(label="Average evaluation score", value=avg_score)

if avg_score >= 0.1:
     st.error("The evaluation failed. Please try again.")

else:
    st.success("The evaluation passed!")



st.dataframe(df)


# append the current timestamp as a column to the dataframe
df['timestamp'] = pd.Timestamp.now()

# append the dataframe to the test/evaluation_output.csv file

df.to_csv('evaluation_output.csv', mode='a', header=False, index=False)









import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import callback, dcc, html
from dash.dependencies import Input, Output
from sklearn.datasets import load_wine

dash.register_page(__name__, path="/wine_demo", name=("Wine demo 😃",), order=1)

####################### DATASET #############################
wine = load_wine()
wine_df = pd.DataFrame(wine.data, columns=wine.feature_names)
wine_df["WineType"] = [wine.target_names[t] for t in wine.target]


####################### BAR CHART #############################
def create_heatmap():
    wine_corr = wine_df.corr(numeric_only=True)
    fig = px.imshow(wine_corr, height=600, color_continuous_scale="RdBu")
    fig = fig.update_layout(paper_bgcolor="#e5ecf6", margin={"t": 0})
    return fig


####################### SCATTER CHART #############################
def create_scatter_chart(x_axis, y_axis):
    fig = px.scatter(
        data_frame=wine_df, x=x_axis, y=y_axis, color="WineType", height=600
    )
    fig.update_traces(
        marker={"size": 15, "opacity": 0.85, "line": {"width": 2, "color": "black"}}
    )
    fig.update_layout(paper_bgcolor="#e5ecf6", margin={"t": 0})
    return fig


####################### HISTOGRAM ###############################
def create_distribution(col_name):
    fig = px.histogram(data_frame=wine_df, x=col_name, height=600, nbins=50)
    fig.update_traces(marker={"line": {"width": 2, "color": "black"}})
    fig.update_layout(
        paper_bgcolor="#e5ecf6",
        margin={"t": 0},
    )
    return fig


####################### FIXED BAR CHART #############################
def create_bar_chart(col_name):
    grouped_df = wine_df.groupby("WineType", as_index=False)[col_name].mean()
    fig = px.bar(
        grouped_df,
        x="WineType",
        y=col_name,
        color="WineType",
        height=600,
    )
    fig.update_traces(marker={"line": {"width": 2, "color": "black"}})
    fig.update_layout(bargap=0.7, paper_bgcolor="#e5ecf6", margin={"t": 0})
    return fig


####################### WIDGETS ################################
dd2 = dcc.Dropdown(
    id="sel_col", options=wine.feature_names, value="malic_acid", clearable=False
)

dd = dcc.Dropdown(
    id="dist_column", options=wine.feature_names, value="alcohol", clearable=False
)
x_axis = dcc.Dropdown(
    id="x_axis", options=wine.feature_names, value="alcohol", clearable=False
)
y_axis = dcc.Dropdown(
    id="y_axis", options=wine.feature_names, value="malic_acid", clearable=False
)


####################### Dataset Table #############################
def create_table():
    fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=wine.feature_names + ["WineType"],
                    align="left",
                ),
                cells=dict(values=wine_df.values.T, align="left"),
            )
        ]
    )
    fig.update_layout(paper_bgcolor="#e5ecf6", margin={"t": 0, "l": 0, "r": 0, "b": 0})
    return fig


####################### PAGE LAYOUT #############################
layout = html.Div(
    children=[
        html.Div(
            children=[
                html.H1("Wine Dataset Overview"),
                "The data is the results of a chemical analysis of wines grown in the same region in Italy by three different cultivators. There are thirteen different measurements taken for different constituents found in the three types of wine.",
                html.Br(),
                html.Br(),
                "This is a copy of UCI ML Wine recognition datasets. (https://archive.ics.uci.edu/ml/machine-learning-databases/wine/wine.data)",
            ]
        ),
        html.Div(
            children=[
                html.H2("Data Variables"),
                "Number of Instances: 178",
                html.Br(),
                "Number of Attributes: 13 numeric, predictive attributes and the class",
                html.Br(),
                html.Br(),
                *[html.Div([html.B(f"- {feature}")]) for feature in wine.feature_names],
                html.Br(),
                html.B("Class"),
                html.Br(),
                html.B("- class_0"),
                html.Br(),
                html.B("- class_1"),
                html.Br(),
                html.B("- class_2"),
            ]
        ),
        html.Br(),
        html.H2("Dataset Explorer", className="fw-bold text-center"),
        dcc.Graph(id="dataset", figure=create_table()),
        html.Br(),
        html.H2(
            "Explore Distribution of Feature Values", className="fw-bold text-center"
        ),
        dd,
        html.Br(),
        dcc.Graph(id="histogram"),
        html.Br(),
        html.H2(
            "Explore Relationship between Features", className="fw-bold text-center"
        ),
        "X-Axis",
        x_axis,
        "Y-Axis",
        y_axis,
        html.Br(),
        dcc.Graph(id="scatter"),
        html.Br(),
        html.H2(
            "Explore Avg Feature Values per Wine Type", className="fw-bold text-center"
        ),
        dd2,
        html.Br(),
        dcc.Graph(id="bar_chart"),
        html.Br(),
        html.H2("Features Correlation Heatmap", className="fw-bold text-center"),
        dcc.Graph(id="heatmap", figure=create_heatmap()),
    ],
    className="p-4 m-2",
    style={"background-color": "#e3f2fd"},
)


####################### CALLBACKS ################################
@callback(
    Output("histogram", "figure"),
    [Input("dist_column", "value")],
)
def update_histogram(dist_column):
    return create_distribution(dist_column)


@callback(
    Output("scatter", "figure"),
    [Input("x_axis", "value"), Input("y_axis", "value")],
)
def update_scatter_chart(x_axis, y_axis):
    return create_scatter_chart(x_axis, y_axis)


@callback(
    Output("bar_chart", "figure"),
    [Input("sel_col", "value")],
)
def update_bar_chart(sel_col):
    return create_bar_chart(sel_col)

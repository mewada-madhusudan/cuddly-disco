Okay, I understand you want to enhance the translator to handle more Alteryx operations, specifically those that don't involve hardware like webcams (which is essentially all standard data processing tools). Based on the PRD, design docs, and the minimal codebase, I'll update the implementation to include more supported tools while maintaining the safety and governance principles.

Here are the key improvements:

1.  **Extended Tool Registry:** Added support for `AlteryxBasePluginsGui.Union`, `AlteryxBasePluginsGui.Select`, `AlteryxBasePluginsGui.Sort`, and refined others.
2.  **Enhanced Parser:** Improved `extract_tool_config` to capture more configuration details relevant to the newly supported tools (e.g., sort fields, select fields).
3.  **Improved DAG Builder:** Better logic for resolving multiple inputs, especially for tools like `Join` and `Union`.
4.  **Advanced Code Generator:** Implemented logic for `Union`, `Select`, and `Sort` operations, along with refined implementations for existing ones based on the design document patterns.
5.  **Better Expression Handling:** Improved the `convert_alteryx_expression_to_pandas` function to handle more Alteryx-specific syntax and functions.

Here are the updated files:

### 1. Updated `yxmd_translator/translator/registry.py`
```python
"""
Tool Registry - Maps Alteryx tools to their Python implementations
This is the definitive source of truth for supported functionality
"""

SUPPORTED_TOOLS = {
    # Input/Output Tools
    "AlteryxBasePluginsGui.InputData": "input_excel",
    "AlteryxBasePluginsGui.OutputData": "output_excel",
    
    # Data Preparation Tools
    "AlteryxBasePluginsGui.Filter": "filter",
    "AlteryxBasePluginsGui.Formula": "formula",
    "AlteryxBasePluginsGui.Select": "select",
    "AlteryxBasePluginsGui.Sort": "sort",
    
    # Join Tools
    "AlteryxBasePluginsGui.Join": "join",
    "AlteryxBasePluginsGui.Union": "union",
    
    # Summary Tools
    "AlteryxBasePluginsGui.Summarize": "summarize",
    
    # NOT SUPPORTED IN MVP (will block auto-conversion)
    "AlteryxBasePluginsGui.Macro": None,
    "AlteryxBasePluginsGui.R": None,
    "AlteryxBasePluginsGui.Python": None,
    "AlteryxBasePluginsGui.BatchMacro": None,
    "AlteryxBasePluginsGui.Spatial": None,
    "AlteryxBasePluginsGui.Predictive": None,
    "AlteryxBasePluginsGui.Download": None, # Web interaction
    "AlteryxBasePluginsGui.Upload": None,   # Web interaction
    "AlteryxBasePluginsGui.Report": None,    # UI interaction
    "AlteryxBasePluginsGui.InteractiveChart": None, # UI interaction
    "AlteryxBasePluginsGui.TextInput": None, # UI interaction
    "AlteryxBasePluginsGui.ListBox": None,   # UI interaction
    "AlteryxBasePluginsGui.DropDown": None,  # UI interaction
    "AlteryxBasePluginsGui.Date": None,      # UI interaction
    "AlteryxBasePluginsGui.CheckBox": None,  # UI interaction
    "AlteryxBasePluginsGui.Button": None,    # UI interaction
    "AlteryxBasePluginsGui.Message": None,   # UI interaction
    "AlteryxBasePluginsGui.ProgressBar": None, # UI interaction
    "AlteryxBasePluginsGui.DragDrop": None,  # UI interaction
    "AlteryxBasePluginsGui.MultiRowFormula": None, # Complex formula, risky
    "AlteryxBasePluginsGui.Sample": None,    # Sampling logic, not core ETL
    "AlteryxBasePluginsGui.AppendFields": None, # Similar to Union but less common, risky
    "AlteryxBasePluginsGui.CreateApp": None, # Creates Alteryx apps, not data processing
    "AlteryxBasePluginsGui.RunCommand": None, # System command execution, security risk
    "AlteryxBasePluginsGui.Ping": None,      # Network utility, not core ETL
    "AlteryxBasePluginsGui.Email": None,     # Communication tool, not core ETL
    "AlteryxBasePluginsGui.Wand": None,      # Image processing, unlikely to be supported
    # Add more UI/Interaction/Web tools here as needed
}

BLOCKING_TOOLS = [
    "AlteryxBasePluginsGui.Macro",
    "AlteryxBasePluginsGui.R",
    "AlteryxBasePluginsGui.Python",
    "AlteryxBasePluginsGui.BatchMacro",
    # Add all unsupported tools that should block
    "AlteryxBasePluginsGui.Spatial",
    "AlteryxBasePluginsGui.Predictive",
    "AlteryxBasePluginsGui.Download",
    "AlteryxBasePluginsGui.Upload",
    "AlteryxBasePluginsGui.Report",
    "AlteryxBasePluginsGui.InteractiveChart",
    "AlteryxBasePluginsGui.TextInput",
    "AlteryxBasePluginsGui.ListBox",
    "AlteryxBasePluginsGui.DropDown",
    "AlteryxBasePluginsGui.Date",
    "AlteryxBasePluginsGui.CheckBox",
    "AlteryxBasePluginsGui.Button",
    "AlteryxBasePluginsGui.Message",
    "AlteryxBasePluginsGui.ProgressBar",
    "AlteryxBasePluginsGui.DragDrop",
    "AlteryxBasePluginsGui.MultiRowFormula",
    "AlteryxBasePluginsGui.Sample",
    "AlteryxBasePluginsGui.AppendFields",
    "AlteryxBasePluginsGui.CreateApp",
    "AlteryxBasePluginsGui.RunCommand",
    "AlteryxBasePluginsGui.Ping",
    "AlteryxBasePluginsGui.Email",
    "AlteryxBasePluginsGui.Wand",
]

RISKY_PATTERNS = [
    r"\[.*\]",  # Dynamic field references
    r"GetFileName",  # Dynamic file paths
    r"Directory",    # File system operations
    r"DateTimeNow",  # Time-dependent operations
    r"Random",       # Random operations
]

def is_supported(tool_type: str) -> bool:
    """Check if a tool type is supported for automatic conversion"""
    return tool_type in SUPPORTED_TOOLS and SUPPORTED_TOOLS[tool_type] is not None

def get_tool_operation(tool_type: str) -> str:
    """Get the Python operation name for a supported tool"""
    return SUPPORTED_TOOLS.get(tool_type)

def is_blocking_tool(tool_type: str) -> bool:
    """Check if a tool type should block the entire workflow from auto-conversion"""
    return tool_type in BLOCKING_TOOLS or not is_supported(tool_type)
```

### 2. Updated `yxmd_translator/translator/parser.py`
```python
from lxml import etree
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def extract_tool_config(tool_element):
    """Extract configuration details specific to each tool type"""
    config = {}
    
    # Get annotations (comments)
    annotation = tool_element.find(".//Annotation")
    if annotation is not None:
        config["annotation"] = annotation.text.strip() if annotation.text else ""
    
    # Get properties
    properties = tool_element.find(".//Properties")
    if properties is not None:
        # Input/Output file paths
        file_path = properties.find(".//File")
        if file_path is not None:
            config["file_path"] = file_path.get("value")
        
        # Sheet name for Excel inputs
        sheet_name = properties.find(".//SheetName")
        if sheet_name is not None:
            config["sheet_name"] = sheet_name.get("value")
        
        # Filter expression
        filter_exp = properties.find(".//Expression")
        if filter_exp is not None:
            config["expression"] = filter_exp.text.strip() if filter_exp.text else ""
        
        # Formulas
        formulas = properties.findall(".//Formula")
        if formulas:
            config["formulas"] = []
            for formula in formulas:
                field = formula.get("field")
                expr = formula.text.strip() if formula.text else ""
                config["formulas"].append({"field": field, "expression": expr})
        
        # Join configuration
        join_fields = properties.findall(".//JoinField")
        if join_fields:
            config["join_fields"] = [field.get("field") for field in join_fields]
            config["join_type"] = properties.get("joinType", "Inner")
        
        # Summarize configuration
        group_by = properties.findall(".//GroupByField")
        if group_by:
            config["group_by"] = [field.get("field") for field in group_by]
        
        agg_fields = properties.findall(".//AggField")
        if agg_fields:
            config["aggregations"] = []
            for field in agg_fields:
                config["aggregations"].append({
                    "field": field.get("field"),
                    "function": field.get("function"),
                    "new_name": field.get("newFieldName")
                })
        
        # Select configuration - capture field selections
        # Look for FieldInfo elements under Properties or similar relevant section
        field_info_elements = properties.findall(".//FieldInfo")
        if field_info_elements:
            selected_fields = []
            for field_info in field_info_elements:
                 # Assuming 'Selected' attribute indicates if field is kept
                 # This might vary depending on exact YXMD structure
                 selected_attr = field_info.get("Selected", "True") # Default to True if not specified
                 if selected_attr.lower() in ['true', '1']: # Consider True or 1 as selected
                     field_name = field_info.get("Name")
                     if field_name:
                         selected_fields.append(field_name)
            if selected_fields:
                config["selected_fields"] = selected_fields
        
        # Sort configuration - capture sort fields and directions
        sort_info_elements = properties.findall(".//SortInfo") # Common element for sort configs
        if sort_info_elements:
            config["sort_fields"] = []
            for sort_info in sort_info_elements:
                field_name = sort_info.get("Field")
                direction = sort_info.get("Direction", "Asc") # Default to Ascending
                if field_name:
                    config["sort_fields"].append({
                        "field": field_name,
                        "ascending": direction.lower() == "asc"
                    })
        
        # Union configuration - typically doesn't need specific config beyond connections
        # We'll handle Union logic based on input connections in the DAG/codegen
        # For now, just confirm it's a Union tool type handled at higher level

    return config

def parse_yxmd(path: str) -> dict:
    """Parse a YXMD file and extract workflow structure and tool configurations"""
    try:
        tree = etree.parse(path)
        root = tree.getroot()
        
        # Extract workflow metadata
        workflow_name = root.find(".//Properties/Name")
        workflow_name = workflow_name.text if workflow_name is not None else Path(path).stem
        
        tools = []
        connections = []

        # Extract tools
        for tool in root.findall(".//Node"):
            tool_id = tool.get("ToolID")
            plugin = tool.find(".//GuiSettings")
            tool_type = plugin.get("Plugin") if plugin is not None else "Unknown"
            
            # Extract detailed configuration
            config = extract_tool_config(tool)
            
            tools.append({
                "id": tool_id,
                "type": tool_type,
                "config": config,
                "xml": etree.tostring(tool, encoding="unicode")
            })
        
        # Extract connections
        for conn in root.findall(".//Connection"):
            connections.append({
                "from": conn.get("From"),
                "to": conn.get("To"),
                "from_output": conn.get("FromOutput", "Output"),
                "to_input": conn.get("ToInput", "Input")
            })
        
        logger.info(f"Successfully parsed workflow: {workflow_name}")
        logger.debug(f"Found {len(tools)} tools and {len(connections)} connections")
        
        return {
            "name": workflow_name,
            "tools": tools,
            "connections": connections,
            "source_path": path
        }
    
    except Exception as e:
        logger.exception(f"Error parsing YXMD file: {str(e)}")
        raise
```

### 3. Updated `yxmd_translator/translator/dag.py`
```python
import logging
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

def build_connection_map(connections):
    """Build adjacency list representation of the workflow graph"""
    graph = defaultdict(list)
    in_degree = defaultdict(int)
    
    for conn in connections:
        source = conn["from"]
        target = conn["to"]
        graph[source].append(target)
        
        # Ensure nodes with no incoming edges are still in in_degree
        if source not in in_degree:
            in_degree[source] = 0
            
        # Increment in-degree for target node
        in_degree[target] = in_degree.get(target, 0) + 1
    
    return graph, in_degree

def topological_sort(graph, in_degree, tools):
    """Perform topological sort to determine execution order"""
    # Initialize queue with nodes having zero in-degree
    queue = deque([node for node, degree in in_degree.items() if degree == 0])
    ordered_tool_ids = []
    
    # Create mapping from tool ID to tool details for quick lookup
    tool_map = {tool["id"]: tool for tool in tools}
    
    while queue:
        node = queue.popleft()
        ordered_tool_ids.append(node)
        
        # Update in-degrees of adjacent nodes
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    # Check if we've included all nodes (detect cycles)
    if len(ordered_tool_ids) != len(tools):
        logger.warning("Cycle detected in workflow graph. Using fallback ordering.")
        # Fallback: sort by tool ID numerically
        ordered_tool_ids = sorted([tool["id"] for tool in tools], key=lambda x: int(x))
    
    # Return tools in execution order
    return [tool_map[tid] for tid in ordered_tool_ids]

def resolve_inputs_for_tool(tool_id, connections, node_map):
    """Resolve which dataframes should be inputs to a specific tool.
    Returns a list of input node IDs."""
    inputs = []
    for conn in connections:
        if conn["to"] == tool_id:
            from_node = conn["from"]
            if from_node in node_map:
                inputs.append(node_map[from_node])
    return inputs

def build_dag(workflow, validation_report):
    """Build a logical DAG from the workflow structure"""
    try:
        tools = workflow["tools"]
        connections = workflow["connections"]
        
        # Build graph representation and perform topological sort
        graph, in_degree = build_connection_map(connections)
        ordered_tools = topological_sort(graph, in_degree, tools)
        
        # Build DAG nodes with execution order
        dag = []
        node_map = {}  # Maps tool IDs to node IDs
        
        for idx, tool in enumerate(ordered_tools):
            tool_id = tool["id"]
            tool_type = tool["type"]
            
            # Resolve inputs to this node
            input_nodes = resolve_inputs_for_tool(tool_id, connections, node_map)
            
            # Generate node ID (df_1, df_2, etc.)
            node_id = f"df_{idx + 1}"
            node_map[tool_id] = node_id
            
            # Get operation type from registry
            operation = None
            if validation_report["status"] != "BLOCKED":
                from translator.registry import get_tool_operation
                operation = get_tool_operation(tool_type)
            
            # Special handling for tools with no inputs (like InputData)
            # Note: Union tools might legitimately have multiple inputs resolved above
            if not input_nodes and "input" not in (operation or "") and operation != "union":
                logger.warning(f"Tool {tool_id} ({tool_type}) has no inputs but is not an input tool or union.")

            dag_node = {
                "node_id": node_id,
                "tool_id": tool_id,
                "operation": operation,
                "tool_type": tool_type,
                "input_nodes": input_nodes,
                "config": tool["config"],
                "annotation": tool["config"].get("annotation", ""),
                "tool_xml": tool["xml"]
            }
            
            dag.append(dag_node)
        
        logger.info(f"Built DAG with {len(dag)} nodes")
        logger.debug(f"DAG structure: {dag}")
        
        return dag
    
    except Exception as e:
        logger.exception(f"Error building DAG: {str(e)}")
        raise
```

### 4. Updated `yxmd_translator/translator/generator.py`
```python
import os
import json
import logging
import yaml
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import re

logger = logging.getLogger(__name__)

def prepare_config(dag, existing_config=None):
    """Prepare configuration structure for YAML output"""
    config = existing_config or {}
    
    # Initialize structure if not present
    if "inputs" not in config:
        config["inputs"] = {}
    if "parameters" not in config:
        config["parameters"] = {}
    if "outputs" not in config:
        config["outputs"] = {}
    
    # Extract Excel inputs
    excel_inputs = [node for node in dag if node["operation"] == "input_excel"]
    for i, node in enumerate(excel_inputs, 1):
        input_name = f"input_{i}"
        if input_name not in config["inputs"]:
            config["inputs"][input_name] = {
                "type": "excel",
                "path": node["config"].get("file_path", f"/path/to/input_{i}.xlsx"),
                "sheet": node["config"].get("sheet_name", "Sheet1")
            }
    
    # Extract Excel outputs
    excel_outputs = [node for node in dag if node["operation"] == "output_excel"]
    for i, node in enumerate(excel_outputs, 1):
        output_name = f"output_{i}"
        if output_name not in config["outputs"]:
            config["outputs"][output_name] = {
                "type": "excel",
                "path": node["config"].get("file_path", f"/path/to/output_{i}.xlsx")
            }
    
    # Extract filter thresholds as parameters
    for node in dag:
        if node["operation"] == "filter" and "expression" in node["config"]:
            expr = node["config"]["expression"]
            # Simple detection of numeric thresholds
            matches = re.findall(r"[><=!]=?\s*([0-9]+\.?[0-9]*)", expr)
            for match in matches:
                param_name = f"threshold_{match.replace('.', '_')}"
                if param_name not in config["parameters"]:
                    config["parameters"][param_name] = float(match) if '.' in match else int(match)
    
    return config

def convert_alteryx_expression_to_pandas(expr: str, input_df_name: str = "df") -> str:
    """Convert Alteryx expression syntax to pandas/Python syntax"""
    if not expr:
        return ""
    
    # Replace Alteryx field references [Field] with pandas column references
    # Be careful with nested brackets like [Field1] + [Field2]
    # This regex finds [content] and replaces it with just content
    expr = re.sub(r'\[(.*?)\]', r'\1', expr)
    
    # Replace Alteryx functions with pandas equivalents
    # Note: These are simplistic mappings, real-world expressions may need more complex logic
    expr = expr.replace("IsNull", f"{input_df_name}.isnull()")
    expr = expr.replace("!", "~") # Logical NOT in pandas
    # IIF(condition, true_val, false_val) -> np.where(condition, true_val, false_val)
    # This is a basic replacement; complex nested IIFs might need recursive parsing
    expr = re.sub(r'IIF\s*\(\s*(.+?)\s*,\s*(.+?)\s*,\s*(.+?)\s*\)', r'np.where(\1, \2, \3)', expr)
    
    # Replace AND/OR with Python equivalents
    expr = expr.replace(" AND ", " & ")
    expr = expr.replace(" OR ", " | ")
    
    # Handle string literals (ensure they are quoted properly after field replacement)
    # This is a simplification - proper parsing would be more robust
    # Alteryx uses double quotes for strings in expressions, which pandas also accepts
    # So this might often work as-is after field reference replacement
    
    # Handle numeric comparisons
    # expr = re.sub(r'([<>=!]=?)\s*""', r'\1 ""', expr) # Handle emp

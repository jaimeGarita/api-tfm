import pandas as pd
from typing import Dict, Any

def clean_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Limpia el DataFrame eliminando o tratando valores nulos y devuelve estadísticas del proceso.
    
    Args:
        df (pd.DataFrame): DataFrame original a limpiar
        
    Returns:
        Dict[str, Any]: Diccionario con el DataFrame limpio y estadísticas
    """
    registros_iniciales = len(df)
    nulos_iniciales = df.isnull().sum().sum()
    
    df_limpio = df.copy()
    
    df_limpio = df_limpio.dropna(how='all')
    
    columnas_numericas = df_limpio.select_dtypes(include=['int64', 'float64']).columns
    for col in columnas_numericas:
        df_limpio[col] = df_limpio[col].fillna(df_limpio[col].median())

    columnas_categoricas = df_limpio.select_dtypes(include=['object']).columns
    for col in columnas_categoricas:
        df_limpio[col] = df_limpio[col].fillna(df_limpio[col].mode()[0])
    
    estadisticas = {
        'df_limpio': df_limpio,
        'registros_iniciales': registros_iniciales,
        'registros_finales': len(df_limpio),
        'nulos_iniciales': nulos_iniciales,
        'nulos_finales': df_limpio.isnull().sum().sum()
    }
    
    return estadisticas 
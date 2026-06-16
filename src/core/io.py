




def importNeuroMod():
    """Import a .nm file from the NeuroMods folder."""
    
    if not NEURO_MODS_DIR.exists():
        print(f"Error: NeuroMods folder not found at:\n{NEURO_MODS_DIR}")
        print("Make sure the 'NeuroMods' folder is next to the executable.")
        return

    nmList = list(NEURO_MODS_DIR.rglob("*.nm"))
    
    if not nmList:
        print("No .nm files found in the NeuroMods folder!")
        return

    print("Available NeuroMods:")
    for i, file in enumerate(nmList):
        print(f"{i}  {file.name}")

    try:
        choice = int(input("\nWhich one would you like to import (index)?: "))
        chosenFile = nmList[choice]
    except (ValueError, IndexError):
        print("Invalid selection!")
        return

    if not chosenFile.is_file():
        print("That is not a valid NeuroMod file!")
        return

    try:
        df = pd.read_csv(chosenFile)
        df["content"] = df["content"].apply(json.loads)

        print(f"Importing {chosenFile.name} ...")
        
        for _, row in df.iterrows():
            updateDB(
                content_dict=row["content"],
                source=row["source"]
            )
        
        print("Import completed successfully!")
        viewAdaptations(option=0)
        
    except Exception as e:
        print(f"Error importing file: {e}")
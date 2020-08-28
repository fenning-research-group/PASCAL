import numpy as np
import itertools

#### name parsing helper functions

def components_to_name(components, delimiter = '_'):
    composition_label = ''
        for c, n in components.items():
            if n > 0:
                composition_label += '{0}{1:.2f}{2}'.format(c, n, delimiter)

    return composition_label[:-1]

def name_to_components(name, factor = 1, delimiter = '_',):
    '''
    given a chemical formula, returns dictionary with individual components/amounts
    expected name format = 'MA0.5_FA0.5_Pb1_I2_Br1'. 
    would return dictionary with keys ['MA, FA', 'Pb', 'I', 'Br'] and values [0.5,.05,1,2,1]*factor
    '''
    components = {}
    for part in name.split(delimiter):
        species = part
        count = 1.0
        for l in range(len(part), 0, -1):
            try:
                count = float(part[-l:])
                species = part[:-l]
                break
            except:
                pass
        components[species] = count * factor
    return components

#### individual solution functions

def calculate_mix(target, volume, solution_sources):
    '''
    given a target composition, target volume, and stock solution sources, calculates the volumes needed
    from individual stocks to achieve target composition

    target: target composition. Will be passed to name_to_components()
            Example: 'MA0.5_FA0.5_Pb1_I2_Br1'
    volume: target volume, in L
    solution_sources: dictionary with stock solution compositions, molarities, solvents, well positions, and available volumes labeled.
            Example:
                    solution_sources = {
                            'MA_Pb_I3': dict(well = 'A1', molarity = 2, solvent = dict(DMSO = 9, DMF = 1), volume = 15e-3),
                            'Cs_I': dict(well = 'A2', molarity = 3, solvent = dict(DMSO = 1), volume = 15e-3),
                            'FA_Pb_I3': dict(well = 'A3', molarity = 1.5, solvent = dict(DMSO = 9, DMF = 1), volume = 15e-3)
                        }
    '''
    target_composition = name_to_components(target)
    wells = [solution_properties['well'] for solution_name, solution_properties in solution_sources.items()]
    num_solutions = len(solution_sources)
    components = list(target_composition.keys())
    num_components = len(components)

    solution_matrix = np.zeros((num_components, num_solutions))    
    for n, (solution_name, solution_properties) in enumerate(solution_sources.items()):
        solution_components = get_components(solution_name, factor = solution_properties['molarity'])
        for m, component_name in enumerate(components):
            if component_name in solution_components:
                solution_matrix[m,n] = solution_components[component_name]
    
    target_matrix = np.zeros((num_components, ))
    for m, (component_name, component_amount) in enumerate(target_composition.items()):
        target_matrix[m] = component_amount
    
    amount_matrix = np.linalg.lstsq(solution_matrix, target_matrix, rcond = None)[0]
    amount_matrix[amount_matrix < 1e-6] = 0 #clean up values that are essentially 0. If we have a significant negative value here, should get caught downstream
    doublecheck = solution_matrix @ amount_matrix
    if np.linalg.norm((doublecheck - target_matrix))/np.linalg.norm(target_matrix) < 0.01: #check that we are within 1% error wrt target composition
        results = {}
        # for solution, solution_volume in zip(solutions, amount_matrix): 
        #     results[solution] = solution_volume * volume
        for well, solution_volume in zip(wells, amount_matrix): 
            results[well] = solution_volume * volume
    else:
        results = False
        print('Error: Unable to generate target solution with current stock solutions.')
        # raise Exception('Unable to generate target solution with current stock solutions.')
    return results
        

#### combining functions to generate experiment mesh

def compositions_spread(compositions, n):
    composition_components = [get_components(s) for s in compositions]
    components = []
    for s in composition_components:
        components += list(s.keys())
    components = np.unique(components)
    
    mat = np.zeros((len(compositions), len(components)))
    for sidx, s in enumerate(composition_components):
        for cidx, c in enumerate(components):
            if c in s:
                mat[sidx, cidx] = s[c]
    
    compositions = []
    for mix in itertools.combinations_with_replacement(mat, n):
        composition_amounts = np.array(mix).mean(axis = 0)
        composition_label = ''
        for c, a in zip(components, composition_amounts):
            if a > 0:
                composition_label += '{0}{1:.3f}_'.format(c, a)
        compositions.append(composition_label[:-1]) #exclude the last underscore

    return list(np.unique(compositions))

def spincoat_spread(spincoats, n):
    mat = np.array(spincoats)
    
    spincoats = []
    for mix in itertools.combinations_with_replacement(mat, n-1):
        spincoats.append(np.array(mix).mean(axis = 0))

    return np.unique(spincoats, axis = 0)

def anneal_spread(anneals, n):
    mat = np.array(anneals)
    
    anneals = []
    for mix in itertools.combinations_with_replacement(mat, n-1):
        anneals.append(np.array(mix).mean(axis = 0))

    return np.unique(anneals, axis = 0)
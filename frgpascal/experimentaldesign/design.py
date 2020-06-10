import numpy as np
import itertools

def components_to_name(components, delimiter = '_'):
    composition_label = ''
        for c, n in components.items():
            if n > 0:
                composition_label += '{0}{1:.2f}{2}'.format(c, n, delimiter)

    return composition_label[:-1]

def name_to_components(name, factor = 1, delimiter = '_',):
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

def calculate_mix(target, volume, solution_sources):
    target_composition = name_to_components(target)
    solutions = list(solution_sources.keys())
    wells = [solution_sources[s]['well'] for s in solutions]
    num_solutions = len(solutions)
    components = list(target_composition.keys())
    num_components = len(components)

    solution_matrix = np.zeros((num_components, num_solutions))    
    for n, solution_name in enumerate(solutions):
        solution_components = name_to_components(solution_name, factor = solution_sources[solution_name]['molarity'])
        for m, component_name in enumerate(components):
            if component_name in solution_components:
                solution_matrix[m,n] = solution_components[component_name]
    
    target_matrix = np.zeros((num_components, ))
    for m, component_name in enumerate(components):
        target_matrix[m] = target_composition[component_name]
    
    amount_matrix = np.linalg.lstsq(solution_matrix, target_matrix, rcond = None)[0]
    amount_matrix[amount_matrix < 1e-6] = 0 #clean up values that are essentially 0. If we have a significant negative value here, should get caught downstream
    doublecheck = solution_matrix @ amount_matrix
    if np.linalg.norm((doublecheck - target_matrix))/np.linalg.norm(target_matrix) < 0.01: #check that we are within 1% error wrt target composition
        results = {}
#         for solution, solution_volume in zip(solutions, amount_matrix): 
#             results[solution] = solution_volume * volume
        for well, solution_volume in zip(wells, amount_matrix): 
            results[well] = solution_volume * volume
    else:
        results = False
        print('Error: Unable to generate target solution with current stock solutions.')
#         raise Exception('Unable to generate target solution with current stock solutions.')
    return results
        

def solutions_spread(solutions, n):
    solution_components = [name_to_components(s) for s in solutions]
    components = []
    for s in solution_components:
        components += list(s.keys())
    components = np.unique(components)
    
    mat = np.zeros((len(solutions), len(components)))
    for sidx, s in enumerate(solution_components):
        for cidx, c in enumerate(components):
            if c in s:
                mat[sidx, cidx] = s[c]
    
    compositions = []
    for mix in itertools.combinations_with_replacement(mat, n):
        composition = np.array(mix).mean(axis = 0)
        composition_label = ''
        for c, n in zip(components, composition):
            if n > 0:
                composition_label += '{0}{1:.2f}_'.format(c, n)
        compositions.append(composition_label[:-1])

    return compositions

def spincoat_spread(spincoats, n):
    mat = np.array(spincoats)
    
    spincoats = []
    for mix in itertools.combinations_with_replacement(mat, n-1):
        spincoats.append(np.array(mix).mean(axis = 0))

    return np.unique(spincoats, axis = 0)

def anneal_spread(anneals, n):
    return spincoat_spread(anneals, n)
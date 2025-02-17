EESchema Schematic File Version 4
EELAYER 30 0
EELAYER END
$Descr A4 11693 8268
encoding utf-8
Sheet 1 1
Title ""
Date ""
Rev ""
Comp ""
Comment1 ""
Comment2 ""
Comment3 ""
Comment4 ""
$EndDescr
$Comp
L Connector:DB25_Female_MountingHoles DB25
U 1 1 60F93072
P 5000 4150
F 0 "DB25" H 5179 4059 50  0000 L CNN
F 1 "DB25_Female_MountingHoles" H 5179 4150 50  0000 L CNN
F 2 "Connector_Dsub:DSUB-25_Male_Horizontal_P2.77x2.84mm_EdgePinOffset7.70mm_Housed_MountingHolesOffset9.12mm" H 5000 4150 50  0001 C CNN
F 3 " ~" H 5000 4150 50  0001 C CNN
	1    5000 4150
	-1   0    0    1   
$EndComp
$Comp
L Connector:Barrel_Jack 5V_1
U 1 1 60F9C187
P 7450 5350
F 0 "5V_1" H 7220 5308 50  0000 R CNN
F 1 "Barrel_Jack" H 7220 5399 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 7500 5310 50  0001 C CNN
F 3 "~" H 7500 5310 50  0001 C CNN
	1    7450 5350
	-1   0    0    1   
$EndComp
$Comp
L Connector:Barrel_Jack 5V_2
U 1 1 60F9D14E
P 7450 5000
F 0 "5V_2" H 7220 4958 50  0000 R CNN
F 1 "Barrel_Jack" H 7220 5049 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 7500 4960 50  0001 C CNN
F 3 "~" H 7500 4960 50  0001 C CNN
	1    7450 5000
	-1   0    0    1   
$EndComp
$Comp
L Connector:Barrel_Jack 5V_3
U 1 1 60F9E991
P 7450 4650
F 0 "5V_3" H 7220 4608 50  0000 R CNN
F 1 "Barrel_Jack" H 7220 4699 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 7500 4610 50  0001 C CNN
F 3 "~" H 7500 4610 50  0001 C CNN
	1    7450 4650
	-1   0    0    1   
$EndComp
Text Label 7400 5700 0    50   ~ 0
5V
Text Label 7400 2500 0    50   ~ 0
12V
Text Label 2300 2400 2    50   ~ 0
24V
Text Label 2300 5800 2    50   ~ 0
Empty
Wire Wire Line
	5300 5350 5300 5450
Wire Wire Line
	5300 5450 7150 5450
Wire Wire Line
	5300 5150 7150 5150
Wire Wire Line
	7150 5150 7150 5100
Wire Wire Line
	7150 4750 6900 4750
Wire Wire Line
	6900 4750 6900 4950
Wire Wire Line
	6900 4950 5300 4950
Wire Wire Line
	7150 4400 6700 4400
Wire Wire Line
	6700 4400 6700 4750
Wire Wire Line
	6700 4750 5300 4750
$Comp
L Connector:Barrel_Jack 12V_1
U 1 1 60FB381C
P 7450 3850
F 0 "12V_1" H 7220 3808 50  0000 R CNN
F 1 "Barrel_Jack" H 7220 3899 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 7500 3810 50  0001 C CNN
F 3 "~" H 7500 3810 50  0001 C CNN
	1    7450 3850
	-1   0    0    1   
$EndComp
$Comp
L Connector:Barrel_Jack 12V_3
U 1 1 60FB3828
P 7450 3150
F 0 "12V_3" H 7220 3108 50  0000 R CNN
F 1 "Barrel_Jack" H 7220 3199 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 7500 3110 50  0001 C CNN
F 3 "~" H 7500 3110 50  0001 C CNN
	1    7450 3150
	-1   0    0    1   
$EndComp
$Comp
L Connector:Barrel_Jack 12V_4
U 1 1 60FB382E
P 7450 2800
F 0 "12V_4" H 7220 2758 50  0000 R CNN
F 1 "Barrel_Jack" H 7220 2849 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 7500 2760 50  0001 C CNN
F 3 "~" H 7500 2760 50  0001 C CNN
	1    7450 2800
	-1   0    0    1   
$EndComp
$Comp
L Connector:Barrel_Jack Free_3
U 1 1 60FB4A93
P 2200 4800
F 0 "Free_3" H 1970 4758 50  0000 R CNN
F 1 "Free_3" H 1970 4849 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 2250 4760 50  0001 C CNN
F 3 "~" H 2250 4760 50  0001 C CNN
	1    2200 4800
	1    0    0    -1  
$EndComp
$Comp
L Connector:Barrel_Jack Free_2
U 1 1 60FB4A99
P 2200 5150
F 0 "Free_2" H 1970 5108 50  0000 R CNN
F 1 "Free_2" H 1970 5199 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 2250 5110 50  0001 C CNN
F 3 "~" H 2250 5110 50  0001 C CNN
	1    2200 5150
	1    0    0    -1  
$EndComp
$Comp
L Connector:Barrel_Jack Free_1
U 1 1 60FB4A9F
P 2200 5500
F 0 "Free_1" H 1970 5458 50  0000 R CNN
F 1 "Free_1" H 1970 5549 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 2250 5460 50  0001 C CNN
F 3 "~" H 2250 5460 50  0001 C CNN
	1    2200 5500
	1    0    0    -1  
$EndComp
$Comp
L Connector:Barrel_Jack 24V_3
U 1 1 60FB6918
P 2200 2950
F 0 "24V_3" H 1970 2908 50  0000 R CNN
F 1 "Barrel_Jack" H 1970 2999 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 2250 2910 50  0001 C CNN
F 3 "~" H 2250 2910 50  0001 C CNN
	1    2200 2950
	1    0    0    -1  
$EndComp
$Comp
L Connector:Barrel_Jack 24V_2
U 1 1 60FB691E
P 2200 3300
F 0 "24V_2" H 1970 3258 50  0000 R CNN
F 1 "Barrel_Jack" H 1970 3349 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 2250 3260 50  0001 C CNN
F 3 "~" H 2250 3260 50  0001 C CNN
	1    2200 3300
	1    0    0    -1  
$EndComp
$Comp
L Connector:Barrel_Jack 24V_1
U 1 1 60FB6924
P 2200 3650
F 0 "24V_1" H 1970 3608 50  0000 R CNN
F 1 "Barrel_Jack" H 1970 3699 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 2250 3610 50  0001 C CNN
F 3 "~" H 2250 3610 50  0001 C CNN
	1    2200 3650
	1    0    0    -1  
$EndComp
Wire Wire Line
	5300 4150 6950 4150
Wire Wire Line
	6950 4150 6950 3600
Wire Wire Line
	6950 3600 7150 3600
Wire Wire Line
	7150 3250 6800 3250
Wire Wire Line
	6800 3250 6800 3950
Wire Wire Line
	6800 3950 5300 3950
Wire Wire Line
	7150 2900 6600 2900
Wire Wire Line
	6600 2900 6600 3750
Wire Wire Line
	6600 3750 5300 3750
$Comp
L Connector:Barrel_Jack 5V_4
U 1 1 60F9ED63
P 7450 4300
F 0 "5V_4" H 7220 4258 50  0000 R CNN
F 1 "Barrel_Jack" H 7220 4349 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 7500 4260 50  0001 C CNN
F 3 "~" H 7500 4260 50  0001 C CNN
	1    7450 4300
	-1   0    0    1   
$EndComp
Wire Wire Line
	7150 5250 7050 5250
Wire Wire Line
	7050 5250 7050 4900
Wire Wire Line
	7050 4900 7150 4900
Wire Wire Line
	7050 4900 7050 4550
Wire Wire Line
	7050 4550 7150 4550
Connection ~ 7050 4900
Wire Wire Line
	7050 4550 7050 4200
Wire Wire Line
	7050 4200 7150 4200
Connection ~ 7050 4550
Wire Wire Line
	5300 4550 7050 4550
Wire Wire Line
	7150 2700 7050 2700
Wire Wire Line
	7050 2700 7050 3050
Wire Wire Line
	7050 3050 7150 3050
Wire Wire Line
	7050 3050 7050 3400
Wire Wire Line
	7050 3400 7150 3400
Connection ~ 7050 3050
Wire Wire Line
	7050 3400 7050 3550
Wire Wire Line
	7050 3750 7150 3750
Connection ~ 7050 3400
Wire Wire Line
	5300 3550 7050 3550
Connection ~ 7050 3550
Wire Wire Line
	7050 3550 7050 3750
Wire Wire Line
	5300 4350 7000 4350
Wire Wire Line
	7000 4350 7000 3950
Wire Wire Line
	7000 3950 7150 3950
Wire Wire Line
	2500 3750 2700 3750
Wire Wire Line
	2700 3750 2700 3400
Wire Wire Line
	2700 3400 2500 3400
Wire Wire Line
	2500 3050 2700 3050
Wire Wire Line
	2700 3050 2700 3400
Connection ~ 2700 3400
Wire Wire Line
	2500 4900 2700 4900
Wire Wire Line
	2700 4900 2700 5250
Wire Wire Line
	2700 5600 2500 5600
Wire Wire Line
	2500 5250 2700 5250
Connection ~ 2700 5250
Wire Wire Line
	2700 5250 2700 5600
Wire Wire Line
	5300 3350 4600 3350
Wire Wire Line
	4600 3350 4600 3550
Wire Wire Line
	4600 3550 2500 3550
Wire Wire Line
	5300 3150 4450 3150
Wire Wire Line
	4450 3150 4450 3200
Wire Wire Line
	4450 3200 2500 3200
Wire Wire Line
	2500 2850 4600 2850
Wire Wire Line
	4600 2850 4600 2950
Wire Wire Line
	4600 2950 5300 2950
Wire Wire Line
	5300 5250 4700 5250
Wire Wire Line
	4700 5250 4700 3400
Wire Wire Line
	4700 3400 2700 3400
Wire Wire Line
	5300 5050 4250 5050
Wire Wire Line
	4250 5050 4250 5400
Wire Wire Line
	4250 5400 2500 5400
Wire Wire Line
	2500 5050 4200 5050
Wire Wire Line
	4200 5050 4200 4850
Wire Wire Line
	4200 4850 5300 4850
Wire Wire Line
	5300 4650 4200 4650
Wire Wire Line
	4200 4650 4200 4700
Wire Wire Line
	4200 4700 2500 4700
Wire Wire Line
	5300 4450 3600 4450
Wire Wire Line
	3600 4450 3600 5250
Wire Wire Line
	3600 5250 2700 5250
$Comp
L Connector:Barrel_Jack 12V_2
U 1 1 60FB3822
P 7450 3500
F 0 "12V_2" H 7220 3458 50  0000 R CNN
F 1 "Barrel_Jack" H 7220 3549 50  0000 R CNN
F 2 "Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal" H 7500 3460 50  0001 C CNN
F 3 "~" H 7500 3460 50  0001 C CNN
	1    7450 3500
	-1   0    0    1   
$EndComp
$EndSCHEMATC

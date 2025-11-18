Overview
This document details PASCAL's custom-designed spin coater, utilizing a drone motor for its hollow shaft which facilitates vacuum suction to secure the substrate. The motor is controlled via a rotary encoder, allowing precise substrate positioning essential for automated processing. The setup requires a Windows machine with Python to send commands; alternatively, a Raspberry Pi may be used to operate the ODrive, though this configuration remains untested.



Parts List
Part	Price	Link
ODRIVE V3.6	$260	https://odriverobotics.com/shop/odrive-v36
8192 CPR ENCODER	$40	https://odriverobotics.com/shop/cui-amt-102
1800kV Brushless motor	$23	https://www.amazon.com/iFlight-1800KV-Brushless-Quadcopter-unibell/dp/B07XYYRWGP
Modular PS 600W 24V 25A	$190	https://www.mouser.com/ProductDetail/Cosel/PJMA600F-24?qs=DRkmTr78QARizXWjL2NKqg%3D%3D&countryCode=US&currencyCode=USD
Vaacum pump	$300	https://www.rocker.com.tw/en/product/lab-pumps/ptfe-coated-chemical-resistant-vacuum-pump/rocker-400c-ptfe-coated-vacuum-pump/
Al-Machined Motor Chuck	$200	https://www.hubs.com/manufacture/?technology=cnc-machining
O-rings	$8	https://www.amazon.com/Assortment-Plusmart-Pressure-Plumbing-Connections/dp/B0BRN1H471/ref=sr_1_3?crid=2V931C3RGIA20&dib=eyJ2IjoiMSJ9.rMalqnjJK4ptQgIJLXaeol0CN2hMWmSikj0mL1o6aGlH5g0-8UIIJyiXwOtEuSjqxBKzqwW-IMcVi-_6pHMGr_V17O1k9zyMj5X0CCneCI-Jw45dT5PRA3iP8sXJPMMB65hSxLmY9sEAnRvApKuByc5BMIBpTVl4fiq46vQLhJXs_yEAJ9ZE8y7I4x47jYTukhg214csptJHL4ErhJntWRZFgNtJlqjsY_1cCjp2F6k.j1-vT5KaGQSVuHFfXLnOroh-s68B_fjaRGQ5Qn03ITc&dib_tag=se&keywords=o+rings&qid=1712552969&sprefix=o+ring%2Caps%2C179&sr=8-3
SLA Printed Peripherals	$10	https://www.amazon.com/OVERTURE-Filament-Consumables-Dimensional-Accuracy/dp/B07PGY2JP1/ref=sr_1_3_pp?dib=eyJ2IjoiMSJ9.SPz8Xg0t9pBHW5vzHC0hcqYxYtXwfa-Yil5LIAxK-nDf3JL1GTkKLyJrApjVsETM4KNQFX0PTiyEjpSvCEeJO5QKM6cQ-r08OafjWC4lTNDPu67BWv0pnhG3ZZ_HfrawVwvNJynrEMEsomfeJCVhNsTjr1BFBFbQpH87o5VaQDwiJH4rlViSL9sBvPO-Piux_RiqL3OfRC7emvw6rOVGAw8aUow_buCBNpMFJfJO4-Q.SG9CzlajxzBXdi_JxmHuRgmdlpNjiI1lcAEBselnEtU&dib_tag=se&keywords=-%2BPLA&qid=1712552942&sr=8-3&th=1
Solenoid Valve	$8	https://www.amazon.com/4inch-Normally-Closed-Electric-Solenoid/dp/B074Z5SDG3/ref=sr_1_3?crid=5POYNORA9EZL&dib=eyJ2IjoiMSJ9.JLsx3y_np7SG8hfKIUtJtWj8VtkfgF_CTbaxIyYoZ5OHgnqSQ8kOew68nTNhAhrPIDTpnumhJRObFIyRSCQiZCXshF3rObQj-HOZV87RKFJ6do-l0fcqZO3ZMh0pw_jtH8uBoLCpnQS4xYqQm-zO0h_RK_vBkP_qY5F-44N056ZKnEJHcm_twtE9Qvi0YZVwB6c-gy3uV4SWPL2bweUyBgrk076l_5p9qJ5PWumZ4mg.hs0sm7t366FhuDrl8LP-5qxEI9jizQlWJ90Q60t1cAI&dib_tag=se&keywords=12v+solenoid+valve&qid=1712552992&sprefix=12v+solenoid+valv%2Caps%2C130&sr=8-3
16 Channel USB Relay Module	$100	https://numato.com/product/16-channel-usb-relay-module/
Installation
Connect the hardware following https://docs.odriverobotics.com/v/0.5.5/getting-started.html

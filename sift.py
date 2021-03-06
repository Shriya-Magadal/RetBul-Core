#!/usr/bin/env python

import cv2
import pandas as pd
import numpy as np
import argparse,sys
import math
import glob
import subprocess
from openpyxl import Workbook, load_workbook
from json_tricks.np import dump, load
from utilities import Utilities


def filter_rawMatches(kp1, kp2, matches, ratio = 0.75):

	mkp1, mkp2 = [], []
	
	for r in range(len(matches)-1):
		if matches[r].distance < ratio * matches[r+1].distance:
			m = matches[r]
			mkp1.append(kp1[m.queryIdx])
			mkp2.append(kp2[m.trainIdx])	
	p1 = np.float32([kp.pt for kp in mkp1])
	p2 = np.float32([kp.pt for kp in mkp2])
	kp_pairs = zip(mkp1, mkp2)	

	return p1,p2,kp_pairs		

def rankingList(index,image_id,n_inliers,percent):

	resList[index][0] = index
	resList[index][1] = image_id
	resList[index][2] = n_inliers
	resList[index][3] = percent		

if __name__ == '__main__':

	parser = argparse.ArgumentParser()

	parser.add_argument('-img1', action='append', dest='im1',             
	                    help='Query Image')
	parser.add_argument('-nF', action='store', dest='nFeatures', type=int,
	                     default=0,help='Number of Features to retain <0-5000>')
	parser.add_argument('-nL', action='store', dest='nOctaveLayers', type=int,
	                     default=3,help='Number of Octave Layers <3-6>')
	parser.add_argument('-cT', action='store',dest='contrastThres', type=float,
						default=0.08,help='Contrast Threshold weak feature filter factor')
	parser.add_argument('-eT', action='store',dest='edgeThres', type=int,
						default=10,help='Edge Threshold edge-like feature factor')
	parser.add_argument('-kpfixed', action='store_true',default=False,
	                    dest='kpfixed',help='Fixed Keypoint Colour')
	parser.add_argument('-v', action='store_true',default=False,
	                    dest='v',help='Save image to file')
	parser.add_argument('-o', action='store_true',default=False,
	                    dest='o',help='Save data to CSV')
	arguments = parser.parse_args()

	if arguments.im1:
		img1Path = str(arguments.im1)[2:-2]
	else:
		parser.print_help()
		print("-img1: Query Image")
		sys.exit(1)

	util = Utilities()

	#image counter
	n = 0
	## Prepare Dataset ##
	dataset = []
	listImages = glob.glob('dataset/*.jpg')
	for i in listImages:
		dataset.append(i.split('/')[-1])
	
	#creating a list of (<image>,#inliers) pairs
	resList = np.zeros( len(dataset) , [('idx', 'int16'), ('imageId', 'a28'), ('inliers', 'int16'), ('percent', 'float') ])

	print("\n================")
	print("Features", arguments.nFeatures)
	print("Octave", arguments.nOctaveLayers)
	print("Contrast Thres", arguments.contrastThres)
	print("Edge Threshold", arguments.edgeThres)
	print("================")

	## SIFT features and descriptor
	sift = cv2.xfeatures2d.SIFT_create(arguments.nFeatures,arguments.nOctaveLayers,arguments.contrastThres,arguments.edgeThres,1.6)	
	## #----------------- # ##
	## Read, Resize, Grayscale Query Image ##
	img1 = cv2.resize(cv2.imread(img1Path, 1), (480, 640))
	img1Gray = cv2.cvtColor(img1,cv2.COLOR_RGB2GRAY )	
	kp1, d1 = sift.detectAndCompute(img1Gray, None)

	for img2Path in dataset:

		print("\nProcessing..")
		print("Test Image:%s (%d/%d) \n" % (img2Path,n+1,len(dataset)))
		## #----------------- # ##
		## Read, Resize, Grayscale Test Image ## 
		img2 = cv2.resize(cv2.imread("dataset/" + img2Path, 1), (480, 640))
		img2Gray = cv2.cvtColor(img2,cv2.COLOR_RGB2GRAY )	
		kp2, d2 = sift.detectAndCompute(img2Gray, None)
	
		## # Use BFMatcher, Euclidian distance, Eliminate Multiples # ##
		bf = cv2.BFMatcher(cv2.NORM_L2,crossCheck=True)
		raw_matches = bf.match(d1,d2)
		src_points, dst_points, kp_pairs = filter_rawMatches(kp1,kp2,raw_matches)	

		print('Matching tentative points in image1: %d, image2: %d' % (len(src_points), len(dst_points)))
		
		## # ----------------# ##
		## # Homography # ##
		print('#----------------#')
		print('Homography')
		print('#----------------#')
		if len(kp_pairs) > 4:
			
			Homography, status = cv2.findHomography(src_points, dst_points, cv2.RANSAC, 5.0)			
			inliers = np.count_nonzero(status)
			percent = float(inliers) / len(kp_pairs)
		
			print("# Inliers %d out of %d tentative pairs" % (inliers,len(kp_pairs)))
			print('Score:' + '{percent:.2%}\n'.format(percent= percent))
			rankingList(n,img2Path,inliers,percent)
		else:
			rankingList(n,img2Path,0,0)
			print("Not enough correspondenses")

		n = n+1
		## Verbose Results
		if arguments.v:

			img1kp = img1
			img2kp = img2
			if arguments.kpfixed:
				img1kp = util.drawKeypoint(img1kp,kp1)
				img2kp = util.drawKeypoint(img2kp,kp2)
			else:			
				cv2.drawKeypoints(img1kp,kp1,img1kp,None,flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
				cv2.drawKeypoints(img2kp,kp2,img2kp,None,flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
				print("Default Keypoints")	
			
			cv2.imshow('Query',img1kp)
			cv2.imshow('Test',img2kp)
			imgTentMatches = cv2.drawMatches(img1kp,kp1,img2kp,kp2,raw_matches,None, flags=2)
			cv2.imshow('Tentative Matches',imgTentMatches)

			try:
				h1, w1, z1 = img1.shape[:3]
				h2, w2, z2 = img2.shape[:3]
				img3 = np.zeros((max(h1, h2), w1+w2,z1), np.uint8)
				img3[:h1, :w1, :z1] = cv2.resize(cv2.imread(img1Path, 1), (480, 640))
				img3[:h2, w1:w1+w2, :z2] = cv2.resize(cv2.imread("dataset/" + img2Path, 1), (480, 640))
				
				p1 = np.int32([kpp[0].pt for kpp in kp_pairs])
				p2 = np.int32([kpp[1].pt for kpp in kp_pairs]) + (w1, 0)
				
				for (x1, y1), (x2, y2), inlier in zip(p1,p2, status):
					if inlier:
						cv2.circle(img3, (x1, y1), 2, (0,250,0), 5)
						cv2.circle(img3, (x2, y2), 2, (0,250,0), 5)
						cv2.line(img3, (x1, y1), (x2, y2), (255,100,0),2)
					else:
						cv2.line(img3, (x1-2, y1-2), (x1+2, y1+2), (0, 0, 255), 3)
						cv2.line(img3, (x1-2, y1+2), (x1+2, y1-2), (0, 0, 255), 3)
						cv2.line(img3, (x2-2, y2-2), (x2+2, y2+2), (0, 0, 255), 3)
						cv2.line(img3, (x2-2, y2+2), (x2+2, y2-2), (0, 0, 255), 3)
			
			except (RuntimeError, TypeError, NameError):
				print("Not enough Inliers")

			cv2.imshow('SIFT Match + Inliers',img3)
			cv2.waitKey(0)
			cv2.destroyAllWindows()		

		#Output CSV
		if arguments.o:
			outFolder = "sift_experiments/"
			util.initWrite()
			util.writeFile(kp2,d2,img1Path,img2Path,inliers,percent,len(kp2))
			util.closeWrite(outFolder,img2Path,'sift')

	print("\n#### Ranking ####")
	rList = np.sort(resList, order= 'inliers')[::-1]
	for bestPair in range(10):
		print('#%d: %s -> Inliers: %d') % (bestPair + 1, rList[bestPair][1], rList[bestPair][2])
		print('{percent:.2%}'.format(percent= rList[bestPair][3]))

	## # Results and Experimental Values Logging # ##
	if arguments.o:
		subprocess.check_output(["sed -e '!d' sift_experiments/sift*.csv >> sift_experiments/sift_" + img1Path[8:-4] +"_merge.csv"], shell=True)
		jList = rList.reshape((n,1))
		with open('results.json','w') as resultFile:
			dump({'Results': jList },resultFile)